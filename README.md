# 🎯 Job Hunter V3 — AI 智能求职助手

基于 **DeepSeek API + agent-browser + Typer CLI** 的 AI 求职助手。
从简历解析到岗位推荐、简历优化、模拟面试一站式闭环。

```bash
python run.py auto -f 简历.md     # 一键全流程
```

---

## 🚀 Quick Start

### 安装

```bash
# Python 3.11+
git clone https://github.com/你的用户名/job-hunter.git
cd job-hunter

# 安装依赖
pip install typer rich httpx pydantic pyyaml loguru jinja2 faiss-cpu

# (可选) 半自动爬虫
npm i -g agent-browser
agent-browser install
```

### 配置

```bash
# 设置 API Key（从 platform.deepseek.com 获取）
set DEEPSEEK_API_KEY=sk-xxx
```

### 一键全流程

```bash
# 准备好你的简历（Markdown格式）
python run.py init -f 简历.md        # 📝 解析简历
python run.py discover                # 🎯 推荐5个方向
python run.py optimize -d 1           # ✨ 优化简历+ATS分析
python run.py dashboard               # 📊 可视化看板
python run.py auto -f 简历.md         # 🚀 一键全流程
```

---

## 🧠 能力

| 命令 | 功能 | 耗时 |
|------|------|:--:|
| `init -f 简历.md` | 解析简历→结构化画像 | ~5s |
| `discover` | 5方向+学习路径+项目建议 | ~30s |
| `optimize -d 1,3` | 简历优化+QA审查+ATS评分+招呼 | ~15s/岗位 |
| `interview --company 腾讯` | 模拟面试+Question Graph+评分 | 互动 |
| `dashboard` | 可视化驾驶舱(浏览器) | ~1s |
| `auto -f 简历.md` | 全流程自动串联 | ~60s |

**典型成本**: 全流程约 $0.002 (~¥0.015)，Token 约 10K。

---

## 📊 数据资产

| 资产 | 规模 | 用法 |
|------|------|------|
| Resume KB | 50+真实源/181 chunks | Optimize 时 Hybrid Search |
| SkillGraph | 30+技能节点 | 人岗匹配评分 |
| Company KB | 7天缓存 | Greeting/Interview 共享 |
| 评测数据集 | 10 JD-Resume 对 | Benchmark 一键跑分 |
| UserMemory | 跨会话持久化 | Dashboard 驱动 |

---

## 🏗️ 架构

```
run.py (Typer CLI + Rich)
  │
SharedContext (统一数据总线)
  │
Planner DAG → Agents(10) → Domain Rules → Repository(JSON/SQLite)
  │
Infrastructure: LLM / Embedding / Cache / EventBus / RetryPolicy / CostMonitor
```

### Agent 清单

| Agent | 功能 |
|-------|------|
| ResumeAgent | 简历→结构化画像（Markdown/PDF/Word） |
| CareerAgent | 5方向推荐 + 学习路径 + 项目建议 + 时间线 |
| OptimizeAgent | 逐JD定制 + RAG Few-shot（ResumeKB检索） |
| QAAgent | 虚构检测4维（经历/技能/年限/数字） |
| ATSAnalyzer | 关键词覆盖/量化/STAR/格式评分 |
| GreetingAgent | 个性化招呼150字内 |
| InterviewAgent | 模拟面试 + Question Graph + Session |
| MatchScorer | Rule + LLM + SkillGraph 三元评分 |
| PlannerAgent | 10任务DAG + Reflection回退重优化 |

---

## 🧪 测试

```bash
pytest tests/test_core.py -q            # 26个单元测试
python evaluation/benchmark.py          # 全量跑分报告
```

---

## 📁 项目结构

```
job-hunter/
├── run.py                   # CLI入口
├── src/
│   ├── agents/             # 10个Agent
│   ├── workflow/           # Planner + Reflection + SharedContext
│   ├── llm/                # DeepSeek + Router + RetryPolicy
│   ├── domain/             # 纯业务规则
│   ├── repository/         # JSON + SQLite
│   ├── evaluator/          # 评分引擎 + SearchPipeline
│   ├── exporter/           # HTML简历 + Dashboard
│   ├── skill_graph/        # 技能图谱
│   └── models/             # Pydantic数据模型
├── knowledge/
│   ├── resume_kb/          # FAISS简历知识库
│   └── graph.json          # 技能图谱定义
├── evaluation/             # 评测框架 + 数据集
├── experiments/            # 实验中心（A/B对比）
├── tests/                  # 26个单元测试
├── prompts/                # 6个Prompt模板
└── templates/              # HTML模板
```

## 📄 License

MIT
