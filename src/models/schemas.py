"""
Pydantic 数据模型 — 全系统统一数据结构
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ─── 用户画像 ─────────────────────────────────────────────

class Skill(BaseModel):
    name: str
    level: str = "熟练"  # 了解/熟练/精通
    years: float = 0.0
    category: str = ""  # 编程语言/框架/数据库/工具/软技能


class WorkExperience(BaseModel):
    company: str
    position: str
    start_date: str  # "YYYY-MM"
    end_date: str    # "YYYY-MM" or "至今"
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    role: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    url: str = ""


class Education(BaseModel):
    school: str
    degree: str  # 本科/硕士/博士
    major: str = ""
    start_date: str = ""
    end_date: str = ""


class UserProfile(BaseModel):
    """用户完整画像"""
    id: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""

    # 核心信息
    summary: str = ""  # 个人简述
    current_position: str = ""
    total_years: float = 0.0
    expected_position: str = ""
    expected_city: str = ""
    expected_salary: str = ""

    # 结构化数据
    skills: list[Skill] = Field(default_factory=list)
    experiences: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    # 扩展
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)


# ─── 岗位方向 ─────────────────────────────────────────────

class LearningItem(BaseModel):
    topic: str
    resource: str = ""       # 推荐资源（文档/课程/书）
    estimated_hours: float = 0.0
    priority: str = "high"   # high/medium/low


class ProjectSuggestion(BaseModel):
    name: str
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    difficulty: str = "medium"


class CareerDirection(BaseModel):
    """AI 推荐的岗位方向"""
    title: str                          # 岗位名称
    match_score: float = 0.0            # 匹配度 0-100
    match_reason: str = ""              # 匹配理由
    skill_gaps: list[str] = Field(default_factory=list)  # 技能缺口
    resume_advice: str = ""             # 简历优化建议
    learning_path: list[LearningItem] = Field(default_factory=list)  # 学习路线
    suggested_projects: list[ProjectSuggestion] = Field(default_factory=list)
    timeline: str = ""                  # 成长时间线
    difficulty: str = "medium"          # 入门难度


# ─── 职位描述 ─────────────────────────────────────────────

class JobDescription(BaseModel):
    """标准化职位描述"""
    id: str = ""
    title: str = ""
    company: str = ""
    salary: str = ""
    city: str = ""
    education: str = ""
    experience_years: int = 0
    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)
    description: str = ""
    industry: str = ""
    source_platform: str = ""
    source_url: str = ""
    raw_text: str = ""

    # JD 分析结果
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    bonus_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


# ─── 匹配结果 ─────────────────────────────────────────────

class MatchResult(BaseModel):
    """人岗匹配结果"""
    job: JobDescription
    rule_score: float = 0.0
    llm_score: float = 0.0
    skill_graph_score: float = 0.0
    final_score: float = 0.0
    match_details: str = ""
    recommendations: list[str] = Field(default_factory=list)


# ─── 优化简历 ─────────────────────────────────────────────

class OptimizedResume(BaseModel):
    """优化后的简历"""
    target_job_id: str = ""
    target_company: str = ""
    target_position: str = ""

    # 各板块优化后内容
    summary: str = ""
    skills_highlight: list[str] = Field(default_factory=list)
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)

    # QA 结果
    qa_passed: bool = True
    qa_risk_level: str = "low"
    qa_warnings: list[str] = Field(default_factory=list)

    # 元数据
    tokens_used: int = 0
    optimization_notes: str = ""


# ─── 招呼消息 ─────────────────────────────────────────────

class GreetingMessage(BaseModel):
    """个性化打招呼消息"""
    target_job_id: str = ""
    target_company: str = ""
    content: str = ""              # 150 字以内
    match_highlights: list[str] = Field(default_factory=list)
    tokens_used: int = 0


# ─── 工作流状态 ───────────────────────────────────────────

class WorkflowState(BaseModel):
    """工作流状态（断点恢复用）"""
    session_id: str = ""
    current_step: str = ""
    completed_steps: list[str] = Field(default_factory=list)
    profile_id: str = ""
    selected_directions: list[int] = Field(default_factory=list)
    selected_jobs: list[str] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
