"""
Experiment Center — V3.15 实验管理
Prompt A/B对比 + 参数网格搜索 + 自动记录最优配置
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger


@dataclass
class Experiment:
    """单次实验记录"""
    id: str
    name: str
    variant: str  # "A" / "B" / "baseline"
    config: dict = field(default_factory=dict)  # {model, temperature, prompt_version, ...}
    metrics: dict = field(default_factory=dict)  # {ats_score, keyword_recall, judge_score, ...}
    timestamp: float = field(default_factory=time.time)
    notes: str = ""


class ExperimentCenter:
    """实验管理中心"""

    def __init__(self, experiments_dir: str | Path | None = None):
        if experiments_dir is None:
            experiments_dir = Path(__file__).parent.parent.parent / "experiments"
        self._dir = Path(experiments_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self._dir / "history.json"
        self._best_path = self._dir / "best_config.json"
        self._history: list[dict] = self._load_history()

    def _load_history(self) -> list[dict]:
        if self._history_path.exists():
            return json.loads(self._history_path.read_text(encoding="utf-8"))
        return []

    def _save_history(self) -> None:
        self._history_path.write_text(json.dumps(self._history, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, exp: Experiment) -> None:
        """记录一次实验"""
        record = {
            "id": exp.id,
            "name": exp.name,
            "variant": exp.variant,
            "config": exp.config,
            "metrics": exp.metrics,
            "timestamp": exp.timestamp,
            "notes": exp.notes,
        }
        self._history.append(record)
        self._save_history()
        self._update_best(exp)
        logger.info(f"实验记录: {exp.id} ({exp.variant}) → metrics={exp.metrics}")

    def _update_best(self, exp: Experiment) -> None:
        """更新最佳配置"""
        best = self.get_best(exp.name)
        current_best_score = best.metrics.get("judge_score", 0) if best else 0
        new_score = exp.metrics.get("judge_score", 0)

        if new_score > current_best_score:
            self._best_path.write_text(json.dumps({
                "name": exp.name,
                "variant": exp.variant,
                "config": exp.config,
                "metrics": exp.metrics,
                "updated_at": time.time(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"🏆 新最佳: {exp.name}/{exp.variant} → judge_score={new_score}")

    def get_best(self, name: str) -> Experiment | None:
        """获取某类实验的最佳配置"""
        if not self._best_path.exists():
            return None
        best = json.loads(self._best_path.read_text(encoding="utf-8"))
        if best.get("name") == name:
            return Experiment(
                id="best", name=name, variant=best.get("variant", ""),
                config=best.get("config", {}), metrics=best.get("metrics", {}),
                timestamp=best.get("updated_at", 0),
            )
        # 从历史中找
        candidates = [h for h in self._history if h["name"] == name]
        if not candidates:
            return None
        best_record = max(candidates, key=lambda h: h["metrics"].get("judge_score", 0))
        return Experiment(
            id=best_record["id"], name=name, variant=best_record["variant"],
            config=best_record["config"], metrics=best_record["metrics"],
            timestamp=best_record["timestamp"],
        )

    def compare(self, name: str, variant_a: str = "A", variant_b: str = "B") -> dict | None:
        """对比两个实验变体"""
        records_a = [h for h in self._history if h["name"] == name and h["variant"] == variant_a]
        records_b = [h for h in self._history if h["name"] == name and h["variant"] == variant_b]

        if not records_a or not records_b:
            return None

        # 取最新一次
        a = records_a[-1]
        b = records_b[-1]

        comparison = {
            "name": name,
            "variant_a": {"variant": variant_a, "config": a["config"], "metrics": a["metrics"]},
            "variant_b": {"variant": variant_b, "config": b["config"], "metrics": b["metrics"]},
            "winner": variant_a if a["metrics"].get("judge_score", 0) >= b["metrics"].get("judge_score", 0) else variant_b,
            "delta": {},
        }

        # 计算各指标差值
        for key in set(list(a["metrics"].keys()) + list(b["metrics"].keys())):
            va = a["metrics"].get(key, 0)
            vb = b["metrics"].get(key, 0)
            comparison["delta"][key] = round(va - vb, 2)

        return comparison

    def grid_search(self, name: str, param_grid: dict[str, list],
                    evaluator_fn, fixed_config: dict | None = None) -> list[Experiment]:
        """
        参数网格搜索
        Args:
            name: 实验名称
            param_grid: {"temperature": [0.1, 0.3, 0.5], "model": ["deepseek-chat", "deepseek-reasoner"]}
            evaluator_fn: 评估函数，接收 config → 返回 metrics dict
            fixed_config: 固定参数
        """
        import itertools

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        experiments = []

        for combo in itertools.product(*values):
            config = dict(zip(keys, combo))
            if fixed_config:
                config.update(fixed_config)

            variant = "-".join(f"{k}={v}" for k, v in config.items())
            exp_id = f"{name}_{variant}_{int(time.time())}"

            logger.info(f"Grid Search: {name}/{variant}")
            metrics = evaluator_fn(config)

            exp = Experiment(
                id=exp_id, name=name, variant=variant,
                config=config, metrics=metrics,
            )
            self.record(exp)
            experiments.append(exp)

        return experiments

    @property
    def summary(self) -> dict:
        """实验总览"""
        names = set(h["name"] for h in self._history)
        result = {}
        for name in names:
            records = [h for h in self._history if h["name"] == name]
            best = max(records, key=lambda h: h["metrics"].get("judge_score", 0))
            result[name] = {
                "total_experiments": len(records),
                "best_variant": best["variant"],
                "best_score": best["metrics"].get("judge_score", 0),
                "variants": list(set(h["variant"] for h in records)),
            }
        return result
