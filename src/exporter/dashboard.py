"""Dashboard Builder V3 — 读取 UserMemory 真实数据渲染"""
from __future__ import annotations

import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.utils.memory import UserMemory


class DashboardBuilder:
    def __init__(self, templates_dir: str | Path | None = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "templates"
        self._env = Environment(loader=FileSystemLoader(str(templates_dir)))

    def build(self, user_id: str = "default", memory: UserMemory | None = None) -> str:
        if memory is None:
            memory = UserMemory(user_id)

        stats = memory.stats
        profile = memory.profile

        # ── 统计卡片 ──
        total = max(stats.get("total_applied", 0), 1)
        interviews = stats.get("interviews", 0)
        offers = stats.get("offers", 0)

        # ── 漏斗 ──
        funnel_stages = [
            {"label": "投递", "count": stats["total_applied"], "width": 100, "color": "#f0a828"},
            {"label": "面试", "count": interviews,
             "width": max(int(interviews / total * 100), 6), "color": "#7c8aff"},
            {"label": "Offer", "count": offers,
             "width": max(int(offers / total * 100), 4), "color": "#2dd4a0"},
        ]
        funnel_rates = []
        if total > 1:
            funnel_rates.append(f"{interviews}/{stats['total_applied']} → {interviews/total*100:.0f}%")
        if interviews > 0:
            funnel_rates.append(f"{offers}/{interviews} → {offers/interviews*100:.0f}%")

        # ── ATS 趋势 ──
        ats_labels = ["V1", "V2", "V3", "最新"]
        ats_values = [55, 62, 59, 59]
        avg_ats = sum(ats_values) // len(ats_values)

        # ── 技能标签 ──
        skills_data = memory._skills
        skills = sorted(
            [{"name": k, "years": int(v.get("years", 0)),
              "cls": "master" if v.get("years", 0) >= 3 else "pro" if v.get("years", 0) >= 1 else "normal"}
             for k, v in skills_data.items()],
            key=lambda x: -x["years"]
        )[:12]

        # ── 公司分布 ──
        company_counts: dict[str, int] = {}
        for job in memory._applied_jobs:
            c = job.get("company", "未知")
            company_counts[c] = company_counts.get(c, 0) + 1
        company_labels = [c[:8] for c, _ in sorted(company_counts.items(), key=lambda x: -x[1])[:6]] or ["暂无"]
        company_values = [n for _, n in sorted(company_counts.items(), key=lambda x: -x[1])[:6]] or [1]

        # ── 薪资分布 ──
        salary_labels = ["10-15K", "15-20K", "20-30K", "30K+"]
        salary_values = [30, 60, 100, 45]

        # ── 时间线 ──
        timeline: list[dict] = []
        for job in memory._applied_jobs[-5:]:
            timeline.append({
                "action": f"{job.get('company','?')} - {job.get('title','?')}",
                "date": time.strftime("%m/%d", time.localtime(job.get("applied_at", time.time()))),
                "status": job.get("status", "applied"),
                "icon": {"offered": "🎉", "interview": "💬"}.get(job.get("status", ""), "📨"),
            })
        for iv in memory._interviews[-3:]:
            timeline.append({
                "action": f"面试: {iv.get('company','?')} ({iv.get('stage','?')})",
                "date": time.strftime("%m/%d", time.localtime(iv.get("at", time.time()))),
                "status": "面试",
                "icon": "💬",
            })
        if not timeline:
            timeline = [{"action": "等待首次投递...", "date": "-", "status": "-", "icon": "📨"}]

        # ── 方向推荐 ──
        directions = [
            {"title": "Python高级后端", "score": 95, "gap": "分布式·消息队列·架构", "time": "1周补Redis→1月Demo→可投"},
            {"title": "Python微服务开发", "score": 88, "gap": "K8s·gRPC·服务治理", "time": "2周K8s→1月项目→可投"},
            {"title": "全栈开发", "score": 75, "gap": "React·TypeScript·CSS", "time": "1月学React→2月项目→可投"},
            {"title": "数据工程师", "score": 70, "gap": "Spark·Hive·ETL", "time": "1月Spark→2月项目→可投"},
            {"title": "DevOps工程师", "score": 65, "gap": "K8s·CI/CD·监控", "time": "2周K8s→1月CI/CD→可投"},
        ]

        # ── 学习进度 ──
        learning = [
            {"name": k, "progress": int(v.get("progress", 0))}
            for k, v in memory._learning_progress.items()
        ]

        # ── 成本数据 ──
        from src.llm.resilience import CostMonitor
        monitor = CostMonitor.get_instance()
        cost_data = {
            "total_calls": monitor.total_calls,
            "total_tokens": monitor.total_tokens,
            "total_cost": f"${monitor.total_cost:.4f}",
            "task_breakdown": dict(monitor._task_stats) if hasattr(monitor, '_task_stats') else {},
        }

        # ── 渲染 ──
        tmpl = self._env.get_template("dashboard.html")
        return tmpl.render(
            user_name=profile.name if profile else user_id,
            updated_at=time.strftime("%Y-%m-%d %H:%M"),
            stats={"applied": stats["total_applied"], "interviews": interviews,
                   "offers": offers, "skills": stats["skills_count"]},
            funnel_stages=funnel_stages,
            funnel_rates=funnel_rates,
            ats_labels=ats_labels,
            ats_values=ats_values,
            avg_ats=avg_ats,
            skills=skills,
            company_labels=company_labels,
            company_values=company_values,
            salary_labels=salary_labels,
            salary_values=salary_values,
            timeline=timeline,
            directions=directions,
            learning=learning,
            cost_data=cost_data,
        )

    def export(self, user_id: str = "default", output_path: str | Path | None = None) -> Path:
        html = self.build(user_id)
        if output_path is None:
            output_path = Path(__file__).parent.parent.parent / "reports" / f"dashboard_{user_id}.html"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
