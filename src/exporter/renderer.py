"""
简历渲染器 — Jinja2 HTML 模板渲染 + 导出
"""

from __future__ import annotations

import json
import os
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader

from src.models.schemas import OptimizedResume, UserProfile


class ResumeRenderer:
    """简历 HTML 渲染 + 导出"""

    def __init__(self, templates_dir: str | Path | None = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "templates"
        self._env = Environment(loader=FileSystemLoader(str(templates_dir)))
        self._templates_dir = Path(templates_dir)

    def render(
        self,
        profile: UserProfile,
        template: str = "professional",
        optimized: OptimizedResume | None = None,
    ) -> str:
        """渲染为 HTML 字符串"""
        tmpl = self._env.get_template(f"{template}.html")

        # 构建模板上下文
        ctx: Dict[str, Any] = {
            "profile": profile,
            "summary": optimized.summary if optimized else profile.summary,
            "skills": self._prepare_skills(profile, optimized),
            "experiences": self._prepare_experiences(profile, optimized),
            "projects": self._prepare_projects(profile, optimized),
            "education": [e.model_dump() for e in profile.education],
            "target_position": optimized.target_position if optimized else profile.expected_position,
            "target_company": optimized.target_company if optimized else "",
        }

        return tmpl.render(**ctx)

    def export_html(
        self,
        profile: UserProfile,
        output_path: str | Path,
        template: str = "professional",
        optimized: OptimizedResume | None = None,
    ) -> Path:
        """导出为 HTML 文件"""
        html = self.render(profile, template=template, optimized=optimized)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def export_and_open(
        self,
        profile: UserProfile,
        output_path: str | Path,
        template: str = "professional",
        optimized: OptimizedResume | None = None,
    ) -> Path:
        """导出 HTML 并在浏览器打开（用户可 Ctrl+P 打印为 PDF）"""
        path = self.export_html(profile, output_path, template=template, optimized=optimized)
        webbrowser.open(f"file://{path.absolute()}")
        return path

    def export_batch(
        self,
        profile: UserProfile,
        output_dir: str | Path,
        optimized_list: list[tuple[str, OptimizedResume | None]],
        template: str = "professional",
    ) -> list[Path]:
        """批量导出：每个岗位一个 HTML 文件"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        for label, opt in optimized_list:
            safe_label = label.replace("/", "-").replace("\\", "-").replace(" ", "_")
            path = output_dir / f"{safe_label}.html"
            self.export_html(profile, path, template=template, optimized=opt)
            paths.append(path)

        return paths

    # ─── 数据准备 ─────────────────────────────────────

    def _prepare_skills(self, profile: UserProfile, optimized: OptimizedResume | None) -> list[dict]:
        if optimized and optimized.skills_highlight:
            result = []
            opt_set = set(optimized.skills_highlight)
            # 优先排列匹配技能
            for s in profile.skills:
                if s.name in opt_set:
                    result.append({"name": s.name, "level": s.level, "years": s.years})
            for s in profile.skills:
                if s.name not in opt_set:
                    result.append({"name": s.name, "level": s.level, "years": s.years})
            return result
        return [{"name": s.name, "level": s.level, "years": s.years} for s in profile.skills]

    def _prepare_experiences(self, profile: UserProfile, optimized: OptimizedResume | None) -> list[dict]:
        if optimized and optimized.experiences:
            return optimized.experiences
        return [e.model_dump() for e in profile.experiences]

    def _prepare_projects(self, profile: UserProfile, optimized: OptimizedResume | None) -> list[dict]:
        if optimized and optimized.projects:
            return optimized.projects
        return [p.model_dump() for p in profile.projects]
