"""
Planner Agent — V3.1 核心升级
任务分配 → 并行/串行决策 → 收集结果 → 冲突解决 → 按需重执行
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from src.workflow.context import AgentResult, BaseAgent, WorkflowContext
from src.workflow.shared_context import SharedContext


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """Planner 管理的任务单元"""
    id: str
    name: str
    agent: BaseAgent | None = None
    fn: Callable | None = None  # 或直接传函数
    kwargs: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # 依赖的任务ID
    status: TaskStatus = TaskStatus.PENDING
    result: AgentResult | None = None
    retries: int = 0
    max_retries: int = 2

    def can_run(self, completed_ids: set[str]) -> bool:
        return all(dep in completed_ids for dep in self.depends_on)


@dataclass
class Plan:
    """执行计划"""
    tasks: list[Task]
    parallel_groups: list[list[str]] = field(default_factory=list)  # 可并行的任务组
    metadata: dict = field(default_factory=dict)


class PlannerAgent(BaseAgent):
    """
    Planner — 智能调度核心
    职责：分析目标 → 生成计划 → 调度执行 → 收集结果 → 冲突解决 → 重执行
    """

    name = "planner"
    description = "智能任务规划与调度中心"

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._results: dict[str, AgentResult] = {}
        self._hooks: dict[str, list[Callable]] = {}  # 任务完成后的钩子

    def plan(self, goal: str, available_agents: dict[str, BaseAgent]) -> Plan:
        """根据目标生成执行计划"""
        logger.info(f"Planner 制定计划: {goal}")

        tasks = []
        parallel_groups = []

        # 根据目标自动编排任务（简化版，后续可接入LLM做动态规划）
        if "search" in goal.lower() or "搜索" in goal:
            tasks = self._plan_search(available_agents)
        elif "optimize" in goal.lower() or "优化" in goal:
            tasks = self._plan_optimize(available_agents)
        elif "full" in goal.lower() or "全流程" in goal or "auto" in goal.lower():
            tasks, parallel_groups = self._plan_full_pipeline(available_agents)
        else:
            tasks = self._plan_full_pipeline(available_agents)[0]

        return Plan(tasks=tasks, parallel_groups=parallel_groups)

    def _plan_search(self, agents: dict) -> list[Task]:
        return [
            Task(id="parse_profile", name="解析画像", agent=agents.get("resume")),
            Task(id="discover", name="发现方向", agent=agents.get("career"), depends_on=["parse_profile"]),
            Task(id="search", name="搜索职位", agent=agents.get("search"), depends_on=["discover"]),
            Task(id="score", name="评分排序", agent=agents.get("matcher"), depends_on=["search"]),
        ]

    def _plan_optimize(self, agents: dict) -> list[Task]:
        return [
            Task(id="parse_profile", name="解析画像", agent=agents.get("resume")),
            Task(id="optimize", name="优化简历", agent=agents.get("optimize"), depends_on=["parse_profile"]),
            Task(id="qa", name="质量审查", agent=agents.get("qa"), depends_on=["optimize"]),
            Task(id="ats", name="ATS分析", agent=agents.get("ats"), depends_on=["optimize"]),
            Task(id="greeting", name="生成招呼", agent=agents.get("greeting"), depends_on=["optimize"]),
            Task(id="export", name="导出", agent=agents.get("export"), depends_on=["qa", "greeting"]),
        ]

    def _plan_full_pipeline(self, agents: dict) -> tuple[list[Task], list[list[str]]]:
        tasks = [
            Task(id="parse_profile", name="解析画像", agent=agents.get("resume")),
            Task(id="discover", name="发现方向", agent=agents.get("career"), depends_on=["parse_profile"]),
            Task(id="search", name="搜索职位", agent=agents.get("search"), depends_on=["discover"]),
            Task(id="jd_analyze", name="JD分析", agent=agents.get("jd"), depends_on=["search"]),
            Task(id="match_score", name="匹配评分", agent=agents.get("matcher"), depends_on=["jd_analyze"]),
        ]
        # 可并行组：多简历优化 + QA + ATS + Greeting
        parallel_groups = [
            ["optimize", "qa", "ats", "greeting"],
        ]
        tasks += [
            Task(id="optimize", name="优化简历", agent=agents.get("optimize"), depends_on=["match_score"]),
            Task(id="qa", name="质量审查", agent=agents.get("qa"), depends_on=["optimize"]),
            Task(id="ats", name="ATS分析", agent=agents.get("ats"), depends_on=["optimize"]),
            Task(id="greeting", name="生成招呼", agent=agents.get("greeting"), depends_on=["optimize"]),
            Task(id="export", name="导出", agent=agents.get("export"), depends_on=["qa", "ats", "greeting"]),
        ]
        return tasks, parallel_groups

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """执行计划"""
        plan: Plan = kwargs.get("plan")
        shared: SharedContext | None = kwargs.get("shared")
        if not plan:
            return AgentResult.fail("未提供执行计划")

        logger.info(f"Planner 开始执行 {len(plan.tasks)} 个任务")
        if shared:
            shared.current_step = "planner"

        self._tasks = {t.id: t for t in plan.tasks}
        self._results = {}
        completed_ids: set[str] = set()

        while len(completed_ids) < len(plan.tasks):
            made_progress = False

            for task in plan.tasks:
                if task.id in completed_ids:
                    continue
                if task.status == TaskStatus.RUNNING:
                    continue
                if not task.can_run(completed_ids):
                    continue

                # 将 SharedContext 注入 task kwargs
                if shared:
                    task.kwargs["shared"] = shared

                self._execute_task(task, ctx)
                made_progress = True

                if task.status == TaskStatus.COMPLETED:
                    completed_ids.add(task.id)
                    self._results[task.id] = task.result
                    # 写回 SharedContext
                    if shared:
                        self._write_to_context(task.id, task.result, shared)

                    # 检查是否需要 Reflection（QA不通过则回退）
                    if task.id == "qa" and task.result and task.result.success:
                        resume = task.result.data
                        if hasattr(resume, 'qa_risk_level') and resume.qa_risk_level == "high":
                            logger.warning("QA不通过(risk=high)，触发回退重优化")
                            # 回退：重置 optimize 和 qa 任务
                            if "optimize" in self._tasks:
                                self._tasks["optimize"].status = TaskStatus.PENDING
                                self._tasks["optimize"].retries += 1
                                if "optimize" in completed_ids:
                                    completed_ids.discard("optimize")
                                if "qa" in completed_ids:
                                    completed_ids.discard("qa")
                                continue

                elif task.status == TaskStatus.FAILED:
                    if task.retries < task.max_retries:
                        logger.warning(f"任务 {task.id} 失败，重试 {task.retries+1}/{task.max_retries}")
                        task.status = TaskStatus.PENDING
                        task.retries += 1
                    else:
                        logger.error(f"任务 {task.id} 超过最大重试次数，跳过")
                        task.status = TaskStatus.SKIPPED
                        completed_ids.add(task.id)

            if not made_progress:
                # 死锁检测：检查是否有无法满足依赖的任务
                stuck = [t.id for t in plan.tasks if t.id not in completed_ids and t.status == TaskStatus.PENDING]
                if stuck:
                    logger.error(f"死锁检测：以下任务无法执行: {stuck}")
                    for sid in stuck:
                        self._tasks[sid].status = TaskStatus.SKIPPED
                        completed_ids.add(sid)
                else:
                    break

        logger.info(f"Planner 完成: {len(completed_ids)}/{len(plan.tasks)} 任务")
        return AgentResult.ok(
            self._results,
            extra={"completed": len(completed_ids), "total": len(plan.tasks)},
        )

    def _write_to_context(self, task_id: str, result: AgentResult, shared: SharedContext) -> None:
        """任务结果写回 SharedContext"""
        if not result.success or not result.data:
            return
        data = result.data

        if task_id == "parse_profile":
            shared.profile = data
        elif task_id == "discover":
            shared.career_directions = data
        elif task_id == "search":
            shared.raw_jobs = data
        elif task_id == "jd_analyze":
            if isinstance(data, list):
                shared.analyzed_jobs = data
            else:
                shared.analyzed_jobs = [data]
        elif task_id == "match_score":
            shared.match_results = data
        elif task_id == "optimize":
            shared.optimized_resume = data
        elif task_id == "qa":
            shared.qa_risk_level = getattr(data, 'qa_risk_level', 'low') if hasattr(data, 'qa_risk_level') else 'low'
            shared.qa_warnings = getattr(data, 'qa_warnings', []) if hasattr(data, 'qa_warnings') else []
        elif task_id == "ats":
            if isinstance(data, dict):
                shared.ats_score = data.get("ats_score", 0)
                shared.ats_details = data.get("details", {})
        elif task_id == "greeting":
            shared.greeting_message = data.content if hasattr(data, 'content') else str(data)

    def _inject_from_context(self, task: Task, shared: SharedContext) -> None:
        """根据任务类型从 SharedContext 自动注入参数"""
        tid = task.id

        if tid == "parse_profile":
            if shared.resume_text and "resume_text" not in task.kwargs:
                task.kwargs["resume_text"] = shared.resume_text
            if shared.profile_name and "profile_name" not in task.kwargs:
                task.kwargs["profile_name"] = shared.profile_name

        elif tid == "discover":
            task.kwargs.setdefault("profile_name", shared.profile_name)

        elif tid == "optimize":
            task.kwargs.setdefault("profile_name", shared.profile_name)
            if shared.top_job() and "job" not in task.kwargs:
                task.kwargs["job"] = shared.top_job()

        elif tid == "qa":
            if shared.profile and "original_profile" not in task.kwargs:
                task.kwargs["original_profile"] = shared.profile
            if shared.optimized_resume and "optimized_resume" not in task.kwargs:
                task.kwargs["optimized_resume"] = shared.optimized_resume

        elif tid == "ats":
            if shared.profile and "profile" not in task.kwargs:
                task.kwargs["profile"] = shared.profile
            if shared.top_job() and "job" not in task.kwargs:
                task.kwargs["job"] = shared.top_job()
            if shared.optimized_resume and "resume" not in task.kwargs:
                task.kwargs["resume"] = shared.optimized_resume

        elif tid == "greeting":
            if shared.profile and "profile" not in task.kwargs:
                task.kwargs["profile"] = shared.profile
            if shared.top_job() and "job" not in task.kwargs:
                task.kwargs["job"] = shared.top_job()

        elif tid == "jd_analyze":
            if shared.raw_jobs and "jd_text" not in task.kwargs:
                task.kwargs["jd_text"] = shared.raw_jobs[0].raw_text or shared.raw_jobs[0].description

        elif tid == "match_score":
            if shared.profile and "profile" not in task.kwargs:
                task.kwargs["profile"] = shared.profile
            if shared.analyzed_jobs and "jobs" not in task.kwargs:
                task.kwargs["jobs"] = shared.analyzed_jobs

        elif tid == "export":
            task.kwargs.setdefault("profile_name", shared.profile_name)

    def _execute_task(self, task: Task, ctx: WorkflowContext) -> None:
        """执行单个任务"""
        task.status = TaskStatus.RUNNING
        logger.info(f"  ▶ {task.name} ({task.id})")

        # 从 SharedContext 自动注入 kwarg
        shared: SharedContext | None = task.kwargs.get("shared")
        if shared:
            self._inject_from_context(task, shared)

        try:
            if task.agent:
                result = task.agent.run(ctx, **task.kwargs)
            elif task.fn:
                result = task.fn(ctx, **task.kwargs)
            else:
                result = AgentResult.fail(f"任务 {task.id} 没有 agent 或 fn")

            task.result = result
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED

            if result.success:
                logger.info(f"  ✅ {task.name} 完成")
            else:
                logger.warning(f"  ❌ {task.name} 失败: {result.error}")
        except Exception as e:
            logger.error(f"  💥 {task.name} 异常: {e}")
            task.result = AgentResult.fail(str(e))
            task.status = TaskStatus.FAILED
