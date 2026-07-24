"""
ATS Analyzer Agent — 简历 ATS（Applicant Tracking System）兼容性分析
评分维度：关键词覆盖、量化程度、STAR结构、排版、长度
"""

from __future__ import annotations

import re
from typing import Any

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import JobDescription, OptimizedResume, UserProfile
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class ATSAnalyzer(BaseAgent):
    """ATS 兼容性分析 Agent"""

    name = "ats_analyzer"
    description = "分析简历的ATS兼容性：关键词覆盖/量化/STAR/排版/长度"

    def __init__(self):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        profile = kwargs.get("profile")
        job = kwargs.get("job")
        resume = kwargs.get("resume")

        if not profile or not job:
            return AgentResult.fail("缺少用户画像或职位信息")

        # 构建简历文本
        resume_text = self._build_resume_text(profile, resume)

        # 1. 规则评分
        keyword_score = self._keyword_coverage(resume_text, job)
        quant_score = self._quantification_score(resume_text)
        star_score = self._star_structure_score(resume_text)
        length_score = self._length_score(resume_text)
        format_score = self._format_score(resume_text)

        rule_total = round(
            keyword_score * 0.35 + quant_score * 0.25 + star_score * 0.20 +
            length_score * 0.10 + format_score * 0.10, 1
        )

        # 2. LLM 综合评分
        llm_score = self._llm_ats_score(resume_text, job)

        final = round(rule_total * 0.5 + llm_score * 0.5, 1)

        result = {
            "ats_score": final,
            "details": {
                "keyword_coverage": keyword_score,
                "quantification": quant_score,
                "star_structure": star_score,
                "length": length_score,
                "format": format_score,
                "llm_score": llm_score,
            },
            "suggestions": self._generate_suggestions(keyword_score, quant_score, star_score),
        }

        return AgentResult.ok(result)

    # ─── 规则评分 ─────────────────────────────────────

    def _keyword_coverage(self, resume_text: str, job: JobDescription) -> float:
        """关键词覆盖率评分"""
        keywords = job.skills_required if job.skills_required else job.hard_skills
        if not keywords:
            return 70.0

        resume_lower = resume_text.lower()
        matched = sum(1 for kw in keywords if kw.lower() in resume_lower)
        ratio = matched / len(keywords)
        return round(min(ratio * 100, 100), 1)

    def _quantification_score(self, resume_text: str) -> float:
        """量化程度评分 — 检测数字、百分比、数据指标"""
        patterns = [
            r'\d+%',                          # 百分比
            r'\d+万',                         # 万级
            r'\d+亿',                         # 亿级
            r'QPS\s*\d+',                     # QPS
            r'\d+\s*倍',                      # 倍数
            r'\d+\s*人',                      # 人数
            r'日均\s*\d+',                    # 日均
            r'月均\s*\d+',                    # 月均
            r'\d+\s*个',                      # 个
        ]
        matches = sum(1 for p in patterns if re.search(p, resume_text, re.IGNORECASE))
        # 期望至少 5 处量化
        return round(min(matches / 5 * 100, 100), 1)

    def _star_structure_score(self, resume_text: str) -> float:
        """STAR 结构评分 — 检测情境/任务/行动/结果描述"""
        star_patterns = [
            r'(负责|主导|参与|领导)',            # Action
            r'(提升|降低|优化|减少|增加|缩短)',   # Result
            r'(从|由|面对|当时|由于)',           # Situation
            r'(设计|开发|实现|搭建|构建)',        # Task
        ]
        matches = sum(1 for p in star_patterns if re.search(p, resume_text, re.IGNORECASE))
        return round(min(matches / 4 * 100, 100), 1)

    def _length_score(self, resume_text: str) -> float:
        """长度评分 — 理想 3000-8000 字符"""
        length = len(resume_text)
        if 3000 <= length <= 8000:
            return 100.0
        if length < 1500:
            return 40.0
        if length < 3000:
            return 60 + (length - 1500) / 1500 * 40
        if length > 10000:
            return 60.0
        return 80 + (10000 - length) / 2000 * 20

    def _format_score(self, resume_text: str) -> float:
        """排版格式评分"""
        score = 100.0
        # 检查是否有基本结构
        if '经历' not in resume_text and 'experience' not in resume_text.lower():
            score -= 20
        if '技能' not in resume_text and 'skill' not in resume_text.lower():
            score -= 20
        if '项目' not in resume_text and 'project' not in resume_text.lower():
            score -= 15
        return max(score, 30)

    # ─── LLM 评分 ─────────────────────────────────────

    def _llm_ats_score(self, resume_text: str, job: JobDescription) -> float:
        """LLM ATS 综合评分"""
        prompt = f"""评估以下简历的ATS（Applicant Tracking System）兼容性，给出0-100分。

目标岗位: {job.title}
要求技能: {', '.join(job.skills_required[:10] if job.skills_required else job.hard_skills[:10])}

简历内容:
{resume_text[:2000]}

评估维度:
1. 关键词覆盖（JD技能是否在简历中出现）
2. 量化程度（是否有数据支撑）
3. 结构清晰度
4. 长度适中

只输出一个0-100的数字。"""

        response = self._llm.generate(prompt, max_tokens=10, temperature=0.1)
        self._cost.record(
            task="ats_analysis",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        try:
            return float(response.content.strip())
        except ValueError:
            return 70.0

    # ─── 辅助 ────────────────────────────────────────

    def _build_resume_text(self, profile: UserProfile, resume: OptimizedResume | None) -> str:
        """构建简历全文"""
        parts = [profile.summary]
        if resume:
            parts.append(resume.summary)
            for _exp in (resume.experiences or []):
                parts.append(f"{_exp.get('company','')} {_exp.get('position','')}: {'; '.join(_exp.get('highlights',[]))}")
            for _proj in (resume.projects or []):
                parts.append(f"{_proj.get('name','')}: {'; '.join(_proj.get('highlights',[]))}")
        else:
            for exp2 in profile.experiences:
                parts.append(f"{exp2.company}: {'; '.join(exp2.highlights)}")
            for proj2 in profile.projects:
                parts.append(f"{proj2.name}: {'; '.join(proj2.highlights)}")
        return '\n'.join(parts)

    def _generate_suggestions(self, kw: float, quant: float, star: float) -> list[str]:
        """生成改进建议"""
        tips = []
        if kw < 70:
            tips.append(f"关键词覆盖率偏低({kw}%)，建议将JD中的技能词自然融入简历")
        if quant < 60:
            tips.append(f"量化描述不足({quant}%)，建议用数字体现成果（如提升x%、日均处理x万）")
        if star < 60:
            tips.append(f"STAR结构较弱({star}%)，建议用'情境→任务→行动→结果'描述经历")
        if kw >= 80 and quant >= 80:
            tips.append("ATS兼容性良好！")
        return tips
