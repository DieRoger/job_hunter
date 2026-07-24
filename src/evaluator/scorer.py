"""
Search 排序器 — 三元评分（Rule + LLM + Skill Graph）集成
"""

from __future__ import annotations

from typing import Any

from src.domain.rules import MatchingDomain
from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import JobDescription, MatchResult, UserProfile
from src.skill_graph.graph import SkillGraph
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class MatchScorer(BaseAgent):
    """人岗匹配评分 Agent — 三元评分"""

    name = "match_scorer"
    description = "对 JD 和用户画像做三元评分：Rule + LLM + Skill Graph"

    def __init__(self):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()
        self._graph = SkillGraph()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        profile = kwargs.get("profile")
        jobs: list[JobDescription] = kwargs.get("jobs", [])

        if profile is None:
            return AgentResult.fail("未提供用户画像")
        if not jobs:
            return AgentResult.fail("未提供职位列表")

        results = []
        for job in jobs:
            match = self.score_single(profile, job)
            results.append(match)

        # 按 final_score 降序排列
        results.sort(key=lambda r: r.final_score, reverse=True)
        return AgentResult.ok(results, extra={"total": len(results)})

    def score_single(self, profile: UserProfile, job: JobDescription) -> MatchResult:
        """对单个 JD 做三元评分"""
        user_skills = [s.name for s in profile.skills]
        jd_skills = job.skills_required if job.skills_required else job.hard_skills

        # 1. Rule Score（硬匹配）
        rule_score = MatchingDomain.rule_score(
            user_skills=set(user_skills),
            jd_skills=set(jd_skills),
            user_years=int(profile.total_years),
            jd_years=job.experience_years,
            user_education=self._edu_level(profile),
            jd_education=job.education,
        )

        # 2. Skill Graph Score
        graph_score = self._graph.compute_graph_score(user_skills, jd_skills)

        # 3. LLM Score（语义评分）
        llm_score = self._llm_score(profile, job, rule_score, graph_score)

        # 加权最终评分
        final = MatchingDomain.weighted_final(rule_score, llm_score, graph_score)

        return MatchResult(
            job=job,
            rule_score=rule_score,
            llm_score=llm_score,
            skill_graph_score=graph_score,
            final_score=final,
            match_details=f"Rule={rule_score} + LLM={llm_score} + Graph={graph_score} → {final}",
        )

    def _llm_score(self, profile: UserProfile, job: JobDescription,
                    rule_score: float, graph_score: float) -> float:
        """LLM 语义评分 — 综合考虑行业/业务/职业发展匹配"""
        prompt = f"""评估候选人与职位的匹配度（0-100分）。

候选人背景:
- 当前岗位: {profile.current_position}
- 技能: {', '.join(s.name for s in profile.skills[:10])}
- 年限: {profile.total_years}年
- 行业: {profile.summary[:100]}

目标职位:
- 岗位: {job.title}
- 公司: {job.company}
- 要求技能: {', '.join(job.skills_required[:10] if job.skills_required else job.hard_skills[:10])}
- 行业: {job.industry}

硬规则评分: {rule_score}/100
技能图谱评分: {graph_score}/100

请给出一个 0-100 的综合语义评分。只输出数字。"""

        response = self._llm.generate(prompt, max_tokens=10, temperature=0.1)
        self._cost.record(
            task="match_score",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        try:
            score = float(response.content.strip())
            return min(max(score, 0), 100)
        except (ValueError, AttributeError):
            # LLM 评分失败时用 Rule+Graph 平均
            return round((rule_score + graph_score) / 2, 1)

    def _edu_level(self, profile: UserProfile) -> str:
        """提取最高学历"""
        levels = {"博士": 7, "硕士": 6, "本科": 5, "大专": 4, "中专": 3, "高中": 2}
        best = ""
        best_lv = 0
        for edu in profile.education:
            lv = levels.get(edu.degree, 0)
            if lv > best_lv:
                best_lv = lv
                best = edu.degree
        return best

    def score_batch(self, profile: UserProfile, jds: list[JobDescription],
                    min_score: float = 50.0) -> list[MatchResult]:
        """批量评分 + 过滤低分"""
        ctx = WorkflowContext()
        result = self.run(ctx, profile=profile, jobs=jds)
        if not result.success:
            return []
        results = result.data or []
        return [r for r in results if r.final_score >= min_score]
