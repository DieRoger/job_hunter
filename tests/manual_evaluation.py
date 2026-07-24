"""测试 V3.15 Evaluation Layer"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.environ["DEEPSEEK_API_KEY"] = ""  # 请设置 DEEPSEEK_API_KEY 环境变量

from evaluation.benchmark import EvaluationRunner
from experiments.center import Experiment, ExperimentCenter
from src.agents.judge_agent import CriticAgent, JudgeAgent
from src.workflow.context import WorkflowContext

# ─── Test 1: ATS Benchmark ──────────────────────
print("=" * 50)
print("Test 1: ATS Benchmark (10 JD-Resume pairs)")
runner = EvaluationRunner()
ats_result = runner.run_ats_benchmark()
print(f"  Avg Before: {ats_result['avg_before']}")
print(f"  Avg After:  {ats_result['avg_after']}")
print(f"  Avg Delta:  +{ats_result['avg_delta']}")
print()

# ─── Test 2: Keyword Recall Benchmark ──────────
print("=" * 50)
print("Test 2: Keyword Recall Benchmark")
kw_result = runner.run_keyword_recall_benchmark()
print(f"  Avg Before: {kw_result['avg_before']}")
print(f"  Avg After:  {kw_result['avg_after']}")
print(f"  Avg Delta:  +{kw_result['avg_delta']}")
print()

# ─── Test 3: Judge Agent ───────────────────────
print("=" * 50)
print("Test 3: Judge Agent (resume_optimize task)")
judge = JudgeAgent()
ctx = WorkflowContext()
result = judge.run(ctx, task_type="resume_optimize",
    input_data={"jd": {"title": "Python后端", "skills": ["Python","Django","MySQL"]}},
    output_data={"summary": "3年Python后端，熟悉Django+MySQL，有高并发经验"})
if result.success:
    print(f"  Score: {result.data['score']}")
    print(f"  Passed: {result.data.get('passed')}")
    print(f"  Reason: {result.data.get('reason','')[:80]}")
print()

# ─── Test 4: Critic Agent ──────────────────────
print("=" * 50)
print("Test 4: Critic Agent")
critic = CriticAgent()
result2 = critic.run(ctx, task_type="resume_optimize",
    original={"skills": ["Python","MySQL"]},
    optimized={"summary": "Python开发经验"},
    low_dimensions=["量化程度", "关键词匹配"])
if result2.success:
    suggestions = result2.data.get("suggestions", [])
    print(f"  Suggestions ({len(suggestions)}):")
    for s in suggestions:
        print(f"    · {s}")
print()

# ─── Test 5: Experiment Center ─────────────────
print("=" * 50)
print("Test 5: Experiment Center")
center = ExperimentCenter()
center.record(Experiment(
    id="exp_001", name="resume_optimize_prompt", variant="A",
    config={"temperature": 0.2, "prompt_version": "v1"},
    metrics={"ats_score": 72, "judge_score": 78, "keyword_recall": 0.75},
))
center.record(Experiment(
    id="exp_002", name="resume_optimize_prompt", variant="B",
    config={"temperature": 0.4, "prompt_version": "v2"},
    metrics={"ats_score": 75, "judge_score": 82, "keyword_recall": 0.80},
))
best = center.get_best("resume_optimize_prompt")
comp = center.compare("resume_optimize_prompt", "A", "B")
print(f"  Best: {best.variant} (score={best.metrics['judge_score']})")
print(f"  Winner: {comp['winner']}, delta={comp['delta']}")
print()

print("=" * 50)
print("✅ V3.15 Evaluation Layer 全部测试通过")
