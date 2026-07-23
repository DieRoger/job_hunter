"""
Resume Agent — 简历解析 + 用户画像生成 + 查漏补缺
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor, RetryPolicy
from src.models.schemas import (
    Education,
    Project,
    Skill,
    UserProfile,
    WorkExperience,
)
from src.repository.store import ProfileRepository
from src.utils.registry import PromptRegistry
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class ResumeAgent(BaseAgent):
    """简历解析 Agent"""

    name = "resume_agent"
    description = "解析简历并生成结构化用户画像"

    def __init__(self):
        self._llm = get_llm_client()
        self._prompts = PromptRegistry.get_instance()
        self._retry = RetryPolicy(max_retries=2, retryable_exceptions=(Exception,))
        self._cost = CostMonitor.get_instance()
        self._repo = ProfileRepository()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """从文本解析简历"""
        resume_text = kwargs.get("resume_text", "")
        profile_name = kwargs.get("profile_name", "default")

        if not resume_text:
            return AgentResult.fail("未提供简历文本")

        logger.info(f"开始解析简历，文本长度: {len(resume_text)}")

        # 调用 LLM 结构化
        prompt = self._prompts.render("profile", resume_text=resume_text)
        response = self._llm.json(prompt)

        # 记录成本
        self._cost.record(
            task="resume_parse",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        # 解析 JSON
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"简历解析 JSON 失败: {e}")
            return AgentResult.fail(f"LLM 返回格式无效: {e}")

        # 构建 UserProfile
        profile = self._build_profile(data)

        # 持久化
        self._repo.save(profile_name, profile.model_dump())
        logger.info(f"用户画像已保存: {profile_name}")

        return AgentResult.ok(
            profile,
            tokens=response.total_tokens,
            duration_ms=response.duration_ms,
        )

    def _build_profile(self, data: dict[str, Any]) -> UserProfile:
        """从 LLM 输出构建 UserProfile"""
        return UserProfile(
            id=data.get("id", ""),
            name=data.get("name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            city=data.get("city", ""),
            summary=data.get("summary", ""),
            current_position=data.get("current_position", ""),
            total_years=data.get("total_years", 0.0),
            expected_position=data.get("expected_position", ""),
            expected_city=data.get("expected_city", ""),
            expected_salary=data.get("expected_salary", ""),
            skills=[Skill(**s) for s in data.get("skills", [])],
            experiences=[WorkExperience(**e) for e in data.get("experiences", [])],
            projects=[Project(**p) for p in data.get("projects", [])],
            education=[Education(**e) for e in data.get("education", [])],
            languages=data.get("languages", []),
            certifications=data.get("certifications", []),
        )

    def parse_file(self, filepath: str | Path) -> str:
        """从文件提取文本"""
        filepath = Path(filepath)
        suffix = filepath.suffix.lower()

        if suffix == ".md":
            return filepath.read_text(encoding="utf-8")

        if suffix == ".txt":
            return filepath.read_text(encoding="utf-8")

        if suffix == ".pdf":
            return self._parse_pdf(filepath)

        if suffix == ".docx":
            return self._parse_docx(filepath)

        raise ValueError(f"不支持的简历格式: {suffix}")

    def _parse_pdf(self, filepath: Path) -> str:
        """PDF 文本提取"""
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n\n".join(text_parts)
        except ImportError:
            raise ImportError("pdfplumber 未安装，无法解析 PDF") from None

    def _parse_docx(self, filepath: Path) -> str:
        """Word 文本提取"""
        try:
            from docx import Document
            doc = Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise ImportError("python-docx 未安装，无法解析 Word") from None


# ─── 交互式查漏补缺 ───────────────────────────────────────

def ask_missing_info(profile: UserProfile) -> list[str]:
    """检查画像缺失项，返回待补充的问题列表"""
    questions = []

    if not profile.expected_position:
        questions.append("期望岗位是什么？")
    if not profile.expected_city:
        questions.append("期望城市是哪里？")
    if not profile.skills:
        questions.append("请列出你的核心技能（至少 3 项）")
    else:
        for skill in profile.skills:
            if skill.years <= 0:
                questions.append(f"'{skill.name}' 的使用年限是多少年？")
            if not skill.level:
                questions.append(f"'{skill.name}' 的熟练度？（了解/熟练/精通）")

    if profile.total_years <= 0 and profile.experiences:
        questions.append("总体工作年限是多少？")

    return questions
