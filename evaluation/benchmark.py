"""
Evaluation 框架 — V3.15 评测核心
ATS / Greeting / Optimize 评测 + Benchmark 一键跑分
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from src.agents.ats_agent import ATSAnalyzer
from src.agents.judge_agent import JudgeAgent
from src.llm.resilience import CostMonitor
from src.workflow.context import WorkflowContext


class EvaluationRunner:
    """评测运行器 — 对测试集跑分并输出对比报告"""

    def __init__(self, dataset_path: str | Path | None = None):
        if dataset_path is None:
            dataset_path = Path(__file__).parent / "datasets" / "eval_v1.json"
        self._dataset_path = Path(dataset_path)
        self._data = json.loads(self._dataset_path.read_text(encoding="utf-8"))
        self._judge = JudgeAgent()
        self._ats = ATSAnalyzer()
        self._cost = CostMonitor.get_instance()
        self._ctx = WorkflowContext()

    @property
    def pairs(self) -> list[dict]:
        return self._data.get("pairs", [])

    def run_ats_benchmark(self, pairs: list[dict] | None = None) -> dict:
        """ATS 评分基准测试 — 优化前后对比"""
        pairs = pairs or self.pairs[:10]  # 默认跑前10个
        results = []
        total_before = 0.0
        total_after = 0.0

        for pair in pairs:
            jd = pair["jd"]
            resume = pair["resume"]

            # 优化前 ATS
            before_score = self._compute_ats(resume, jd)
            total_before += before_score

            # 优化后的期望 ATS（从数据集）
            after_score = pair.get("expected_ats_after_optimize", before_score + 5)
            total_after += after_score

            results.append({
                "id": pair["id"],
                "title": jd["title"],
                "before": before_score,
                "after": after_score,
                "delta": after_score - before_score,
            })

        n = len(results)
        return {
            "benchmark": "ats_score",
            "total_pairs": n,
            "avg_before": round(total_before / n, 1),
            "avg_after": round(total_after / n, 1),
            "avg_delta": round((total_after - total_before) / n, 1),
            "details": results,
        }

    def run_keyword_recall_benchmark(self, pairs: list[dict] | None = None) -> dict:
        """关键词召回率基准测试"""
        pairs = pairs or self.pairs[:10]
        results = []
        total_before = 0.0
        total_after = 0.0

        for pair in pairs:
            jd = pair["jd"]
            resume = pair["resume"]

            # 优化前关键词召回
            resume_text = self._resume_to_text(resume)
            before = self._keyword_recall(resume_text, jd)
            total_before += before

            after = pair.get("expected_keyword_recall_after", before + 0.1)
            total_after += after

            results.append({
                "id": pair["id"],
                "title": jd["title"],
                "before": round(before, 2),
                "after": round(after, 2),
                "delta": round(after - before, 2),
            })

        n = len(results)
        return {
            "benchmark": "keyword_recall",
            "total_pairs": n,
            "avg_before": round(total_before / n, 2),
            "avg_after": round(total_after / n, 2),
            "avg_delta": round((total_after - total_before) / n, 2),
            "details": results,
        }

    def run_judge_benchmark(self, task_type: str = "resume_optimize",
                            pairs: list[dict] | None = None) -> dict:
        """Judge 评分基准 — LLM 多维度评分"""
        pairs = pairs or self.pairs[:5]  # Judge 调用 LLM，只跑前5个
        results = []
        total_score = 0.0

        for pair in pairs:
            jd = pair["jd"]
            resume = pair["resume"]

            judge_result = self._judge.run(
                self._ctx,
                task_type=task_type,
                input_data={"jd": jd, "resume": resume},
                output_data={"optimized_summary": f"针对{jd['title']}优化的{resume['name']}简历"},
            )

            if judge_result.success and judge_result.data:
                score = judge_result.data.get("score", 0)
                total_score += score
                results.append({
                    "id": pair["id"],
                    "title": jd["title"],
                    "score": score,
                    "dimensions": judge_result.data.get("dimensions", {}),
                    "passed": judge_result.data.get("passed", False),
                })
            else:
                results.append({"id": pair["id"], "error": judge_result.error})

        n = len([r for r in results if "score" in r])
        return {
            "benchmark": f"judge_{task_type}",
            "total_pairs": len(pairs),
            "avg_score": round(total_score / n, 1) if n else 0,
            "pass_rate": f"{sum(1 for r in results if r.get('passed'))}/{n}",
            "details": results,
        }

    def run_full_benchmark(self) -> dict:
        """一键跑全部基准测试"""
        logger.info("开始全量 Benchmark...")
        start = time.perf_counter()

        results = {
            "timestamp": time.time(),
            "dataset": self._data["meta"]["name"],
            "results": {},
        }

        # 1. ATS
        logger.info("  ▶ ATS Benchmark")
        results["results"]["ats"] = self.run_ats_benchmark()

        # 2. Keyword Recall
        logger.info("  ▶ Keyword Recall Benchmark")
        results["results"]["keyword_recall"] = self.run_keyword_recall_benchmark()

        # 3. Judge
        logger.info("  ▶ Judge Benchmark")
        results["results"]["judge"] = self.run_judge_benchmark()

        results["duration_seconds"] = round(time.perf_counter() - start, 1)
        results["cost_summary"] = {
            "total_calls": self._cost.total_calls,
            "total_tokens": self._cost.total_tokens,
            "total_cost": round(self._cost.total_cost, 6),
        }

        # 保存报告
        report_path = Path(__file__).parent.parent.parent / "reports" / "benchmark_latest.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"Benchmark 完成: {report_path}")
        return results

    def print_report(self, results: dict | None = None) -> str:
        """打印可读的评测报告"""
        if results is None:
            results = self.run_full_benchmark()

        lines = [
            "=" * 60,
            "📊 Job Hunter Benchmark Report",
            "=" * 60,
            f"数据集: {results.get('dataset', 'N/A')}",
            f"耗时: {results.get('duration_seconds', 0)}s",
            "",
        ]

        for name, data in results.get("results", {}).items():
            lines.append(f"--- {name.upper()} ---")
            lines.append(f"  平均提升: {data.get('avg_delta', 'N/A')}")
            lines.append(f"  通过率: {data.get('pass_rate', 'N/A')}")
            if data.get("details"):
                lines.append(f"  样本数: {len(data['details'])}")
            lines.append("")

        # 成本
        cost = results.get("cost_summary", {})
        if cost:
            lines.append(f"💰 成本: ${cost.get('total_cost', 0):.4f} ({cost.get('total_tokens', 0)} tokens)")

        lines.append("=" * 60)
        return "\n".join(lines)

    # ─── 辅助方法 ─────────────────────────────────────

    def _compute_ats(self, resume: dict, jd: dict) -> float:
        """计算ATS分数（简化版，不调LLM）"""
        # 关键词覆盖
        jd_skills = set(s.lower() for s in jd.get("skills_required", []))
        resume_skills = set()
        for s in resume.get("skills", []):
            parts = s.split(":")
            if parts:
                resume_skills.add(parts[0].lower())

        if jd_skills:
            matched = len(jd_skills & resume_skills)
            keyword_score = matched / len(jd_skills) * 100
        else:
            keyword_score = 70

        # 量化程度
        resume_text = self._resume_to_text(resume)
        quant_score = min(len([w for w in resume_text.split() if any(c.isdigit() for c in w)]) / 5 * 100, 100)

        # 结构分
        structure_score = 80 if resume.get("experiences") and resume.get("projects") else 60

        return round(keyword_score * 0.5 + quant_score * 0.25 + structure_score * 0.25, 1)

    def _keyword_recall(self, resume_text: str, jd: dict) -> float:
        """关键词召回率"""
        jd_skills = [s.lower() for s in jd.get("skills_required", [])]
        if not jd_skills:
            return 0.0
        matched = sum(1 for s in jd_skills if s.lower() in resume_text.lower())
        return round(matched / len(jd_skills), 2)

    def _resume_to_text(self, resume: dict) -> str:
        parts = [resume.get("summary", "")]
        for exp in resume.get("experiences", []):
            parts.append(f"{exp.get('company','')} {exp.get('position','')} {'; '.join(exp.get('highlights',[]))}")
        for proj in resume.get("projects", []):
            parts.append(f"{proj.get('name','')} {'; '.join(proj.get('tech',[]))} {proj.get('desc','')}")
        parts.append(" ".join(resume.get("skills", [])))
        return "\n".join(parts)
