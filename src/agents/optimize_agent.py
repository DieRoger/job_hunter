"""
Resume Optimize Agent — 针对 JD 定制简历
QA Agent — 虚构检测
Greeting Agent — 个性化招呼生成
"""

from __future__ import annotations

import json
from typing import Any

from src.domain.rules import QADomain
from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import (
    GreetingMessage,
    JobDescription,
    OptimizedResume,
    UserProfile,
)
from src.repository.store import ProfileRepository, ResumeRepository
from src.utils.registry import PromptRegistry
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext

# ─── Resume Optimize Agent ────────────────────────────────

class ResumeOptimizeAgent(BaseAgent):
    """简历优化 Agent"""

    name = "resume_optimize_agent"
    description = "针对特定 JD 优化简历，硬约束不编造"

    def __init__(self):
        self._llm = get_llm_client()
        self._prompts = PromptRegistry.get_instance()
        self._cost = CostMonitor.get_instance()
        self._repo = ProfileRepository()
        self._resume_repo = ResumeRepository()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        profile_name = kwargs.get("profile_name", "default")
        job = kwargs.get("job")

        if job is None:
            return AgentResult.fail("未提供目标职位")

        profile_data = self._repo.load(profile_name)
        if profile_data is None:
            return AgentResult.fail(f"用户画像不存在: {profile_name}")

        profile = UserProfile(**profile_data)

        # 使用 reasoner 模型
        from src.llm.router import LLMRouter
        router = LLMRouter(self._llm)
        model = router.resolve_model("resume_optimize")

        # 手动构建优化 Prompt（后续迁移到 prompts/optimize_resume.md）
        prompt = self._build_prompt(profile, job)
        response = self._llm.json(prompt, model=model)

        self._cost.record(
            task="resume_optimize",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            return AgentResult.fail(f"优化结果 JSON 无效: {e}")

        resume = OptimizedResume(
            target_job_id=job.id,
            target_company=job.company,
            target_position=job.title,
            summary=data.get("summary", ""),
            skills_highlight=data.get("skills_highlight", []),
            experiences=data.get("experiences", []),
            projects=data.get("projects", []),
            tokens_used=response.total_tokens,
        )

        # 持久化
        key = f"{profile_name}_{job.company}_{job.title}"
        self._resume_repo.save(key, resume.model_dump())

        return AgentResult.ok(resume, tokens=response.total_tokens)

    def _build_prompt(self, profile: UserProfile, job: JobDescription) -> str:
        """构建优化 Prompt（含 RAG Few-shot）"""
        original_skills = [s.name for s in profile.skills]
        original_companies = [e.company for e in profile.experiences]
        original_projects = [p.name for p in profile.projects]

        # RAG: 检索相关优秀简历 chunk
        rag_examples = ""
        try:
            from knowledge.resume_kb import ResumeKB  # type: ignore[attr-defined]
            kb = ResumeKB()
            query = f"{job.title} {' '.join(job.skills_required[:5] if job.skills_required else job.hard_skills[:5])}"
            chunks = kb.hybrid_search(query, top_k=3)
            if chunks:
                rag_examples = "\n# 参考优秀简历片段（风格参考，不要照抄）\n"
                for i, c in enumerate(chunks, 1):
                    rag_examples += f"\n参考{i} [{c['type']}]: {c['text'][:300]}\n"
        except Exception:
            pass  # KB不可用时降级

        return f"""你是一位资深简历优化师。根据目标 JD 优化候选人的简历。
{rag_examples}
# 核心规则（严格遵守）
1. 只能基于用户已有的经历重组措辞，绝对不能编造新经历
2. 已有公司列表: {original_companies}，不能新增公司
3. 已有项目列表: {original_projects}，不能伪造项目
4. 技能可以调整措辞和侧重点，但不能新增用户不具备的技能
5. 已有技能: {original_skills}

# 用户画像
{json.dumps(profile.model_dump(exclude={'id'}), ensure_ascii=False, indent=2)}

# 目标职位
- 公司: {job.company}
- 岗位: {job.title}
- 要求技能: {', '.join(job.skills_required)}
- 加分项: {', '.join(job.hard_skills)}

# 优化策略
- ATS 友好：关键词自然融入
- 项目重排：与 JD 最相关的项目放在前面
- 技能重排：匹配的技能放在前面
- 经历描述：突出与 JD 相关的成果，用数据说话

# 输出 JSON
{{
  "summary": "个人简述（100字内，突出与JD匹配点）",
  "skills_highlight": ["技能1", "技能2"],
  "experiences": [{{"company": "公司", "position": "职位", "highlights": ["成果1"]}}],
  "projects": [{{"name": "项目名", "highlights": ["亮点1"]}}]
}}
"""


# ─── QA Agent ─────────────────────────────────────────────

class QAAgent(BaseAgent):
    """质量审核 Agent — 虚构检测"""

    name = "qa_agent"
    description = "检查优化后简历是否有虚构内容"

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        original = kwargs.get("original_profile")
        optimized = kwargs.get("optimized_resume")

        if original is None or optimized is None:
            return AgentResult.fail("缺少原始画像或优化简历")

        issues = []

        # 1. 检查虚构经历
        orig_companies = {e.company for e in original.experiences}
        for exp in optimized.experiences:
            company = exp.get("company", "")
            if company and company not in orig_companies:
                issues.append({
                    "type": "possible_fabricated_experience",
                    "company": company,
                    "severity": "high",
                })

        # 2. 检查技能膨胀
        orig_skills = {s.name for s in original.skills}
        opt_skills = set(optimized.skills_highlight)
        new_skills = opt_skills - orig_skills
        if new_skills:
            issues.append({
                "type": "skill_inflation",
                "new_skills": list(new_skills),
                "severity": "high",
            })

        # 3. 检查年限
        from src.domain.rules import ResumeDomain
        orig_years = original.total_years
        # 从优化后经历推算年限（简化：按经历数量×2估算）
        claimed_years = len(optimized.experiences) * 2
        ok, dev = ResumeDomain.check_years_exaggeration(claimed_years, int(orig_years))
        if not ok:
            issues.append({
                "type": "years_exaggeration",
                "deviation": dev,
                "severity": "medium",
            })

        # 评估风险
        risk_level = QADomain.assess_risk(issues)
        passed = risk_level != "high"

        optimized.qa_passed = passed
        optimized.qa_risk_level = risk_level
        optimized.qa_warnings = [f"{i['type']}: {i.get('company', i.get('new_skills', ''))}" for i in issues]

        if not passed:
            return AgentResult.ok(optimized, warnings=[f"QA 不通过 ({risk_level}): 需要重新优化"])

        return AgentResult.ok(optimized, warnings=optimized.qa_warnings if optimized.qa_warnings else [])


# ─── Greeting Agent ───────────────────────────────────────

class GreetingAgent(BaseAgent):
    """打招呼消息生成 Agent"""

    name = "greeting_agent"
    description = "生成个性化 BOSS 打招呼消息（150字内）"

    def __init__(self):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        profile = kwargs.get("profile")
        job = kwargs.get("job")

        if profile is None or job is None:
            return AgentResult.fail("缺少用户画像或职位信息")

        prompt = f"""为 BOSS直聘生成一条打招呼消息，要求：
- 150字以内
- 自然不模板化
- 突出 2-3 个与岗位最匹配的点
- 体现对公司和岗位的了解

候选人背景: {profile.summary}
目标公司: {job.company}
目标岗位: {job.title}
岗位要求: {', '.join(job.skills_required[:5])}

只输出打招呼文本，不要其他内容。"""

        response = self._llm.generate(prompt, max_tokens=300)

        self._cost.record(
            task="greeting",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        greeting = GreetingMessage(
            target_job_id=job.id,
            target_company=job.company,
            content=response.content.strip()[:200],
            tokens_used=response.total_tokens,
        )

        return AgentResult.ok(greeting, tokens=response.total_tokens)
