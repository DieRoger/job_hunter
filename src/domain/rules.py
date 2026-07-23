"""
Domain Layer — 纯业务规则，不含 IO
Agent 和 Service 都调用 Domain 层方法
"""

from __future__ import annotations

import math
from typing import Any


class ResumeDomain:
    """简历业务规则"""

    @staticmethod
    def check_skill_inflation(original_skills: set[str], optimized_skills: set[str],
                               max_inflation: float = 0.15) -> tuple[bool, float]:
        """
        检查技能膨胀率。
        返回 (是否通过, 膨胀率)
        """
        original_count = len(original_skills)
        if original_count == 0:
            return True, 0.0

        new_skills = optimized_skills - original_skills
        inflation = len(new_skills) / original_count
        return inflation <= max_inflation, inflation

    @staticmethod
    def check_experience_continuity(experiences: list[dict]) -> list[str]:
        """检查工作经历时间连续性，返回冲突列表"""
        conflicts = []
        sorted_exp = sorted(experiences, key=lambda e: e.get("start_date", ""))

        for i in range(len(sorted_exp) - 1):
            current_end = sorted_exp[i].get("end_date", "")
            next_start = sorted_exp[i + 1].get("start_date", "")
            if current_end and next_start and current_end > next_start:
                conflicts.append(
                    f"时间重叠: {sorted_exp[i].get('company')}({current_end}) "
                    f"vs {sorted_exp[i+1].get('company')}({next_start})"
                )
        return conflicts

    @staticmethod
    def check_years_exaggeration(claimed_years: int, actual_years: int,
                                  max_deviation: int = 2) -> tuple[bool, int]:
        """检查年限夸大，允许最大偏差 2 年"""
        deviation = claimed_years - actual_years
        return deviation <= max_deviation, deviation


class MatchingDomain:
    """人岗匹配业务规则"""

    @staticmethod
    def rule_score(user_skills: set[str], jd_skills: set[str],
                   user_years: int, jd_years: int,
                   user_education: str, jd_education: str) -> float:
        """硬规则评分（0-100）"""
        # 技能匹配 (50%)
        if not jd_skills:
            skill_score = 50.0
        else:
            matched = len(user_skills & jd_skills)
            skill_score = (matched / len(jd_skills)) * 50

        # 年限匹配 (30%)
        if jd_years <= 0:
            year_score = 30.0
        elif user_years >= jd_years:
            year_score = 30.0
        else:
            year_score = (user_years / jd_years) * 30

        # 学历匹配 (20%)
        edu_levels = {"初中": 1, "高中": 2, "中专": 3, "大专": 4, "本科": 5, "硕士": 6, "博士": 7}
        user_edu = edu_levels.get(user_education, 0)
        jd_edu = edu_levels.get(jd_education, 0)
        if jd_edu <= 0 or user_edu >= jd_edu:
            edu_score = 20.0
        else:
            edu_score = (user_edu / jd_edu) * 20

        return round(skill_score + year_score + edu_score, 1)

    @staticmethod
    def weighted_final(rule_score: float, llm_score: float, skill_graph_score: float,
                       weights: tuple[float, float, float] = (0.4, 0.35, 0.25)) -> float:
        """加权最终评分"""
        rw, lw, sw = weights
        return round(rule_score * rw + llm_score * lw + skill_graph_score * sw, 1)


class QADomain:
    """质量审核业务规则"""

    @staticmethod
    def detect_fabricated_content(
        original_experiences: list[dict],
        optimized_experiences: list[dict],
    ) -> list[dict[str, Any]]:
        """检测虚构经历，返回可疑项列表"""
        issues = []
        orig_companies = {e.get("company", "") for e in original_experiences}

        for exp in optimized_experiences:
            company = exp.get("company", "")
            if company and company not in orig_companies:
                issues.append({
                    "type": "possible_fabricated_experience",
                    "company": company,
                    "severity": "high",
                })
        return issues

    @staticmethod
    def assess_risk(issues: list[dict]) -> str:
        """根据问题评估风险等级: high / medium / low"""
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for issue in issues:
            sev = issue.get("severity", "low")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        if severity_counts["high"] > 0:
            return "high"
        if severity_counts["medium"] > 1:
            return "medium"
        if severity_counts["low"] > 3:
            return "medium"
        return "low"
