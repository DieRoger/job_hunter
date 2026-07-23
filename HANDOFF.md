# Job Hunter V3 — 项目交接文档

## 项目概述

AI 智能求职助手。基于 DeepSeek API，从简历解析到岗位推荐、简历优化、模拟面试一站式闭环。

- **仓库**: https://github.com/DieRoger/job_hunter
- **主入口**: `python run.py --help`
- **核心依赖**: Python 3.11+, DeepSeek API, Typer/Rich, FAISS, Jinja2

---

## 快速上手（新成员）

```bash
git clone https://github.com/DieRoger/job_hunter.git
cd job_hunter
pip install typer rich httpx pydantic pyyaml loguru jinja2 faiss-cpu
set DEEPSEEK_API_KEY=sk-xxx
python run.py auto -f sample_resume.md
```

---

## 架构

```
run.py (Typer CLI + Rich)
  │
SharedContext (统一数据总线 — 所有 Agent 读写此对象)
  │
PlannerAgent (DAG 调度 + Reflection 回路)
  │
Agents (10+) ──→ Domain Rules ──→ Repository (JSON / SQLite)
  │
Infrastructure: LLM / Embedding / Cache / EventBus / RetryPolicy / CostMonitor
```

### 四层设计

| 层 | 目录 | 职责 |
|----|------|------|
| CLI | `run.py` | 9 命令入口（Typer + Rich 美化） |
| Agent | `src/agents/` | 单一职责，继承 BaseAgent |
| Domain | `src/domain/` | 纯业务规则，不含 IO |
| Repository | `src/repository/` | JSON + SQLite 双存储 |

---

## Agent 清单（完整可用）

| Agent | 文件 | 功能 | 状态 |
|-------|------|------|:--:|
| ResumeAgent | `agents/resume_agent.py` | 简历→结构化画像（MD/PDF/Word） | ✅ |
| CareerAgent | `agents/career_agent.py` | 5方向推荐+学习路径+项目建议+时间线 | ✅ |
| JDAnalysisAgent | `agents/jd_agent.py` | JD 硬技能/软技能/加分项提取 | ✅ |
| ResumeOptimizeAgent | `agents/optimize_agent.py` | 逐 JD 定制 + RAG Few-shot（ResumeKB 检索） | ✅ |
| QAAgent | `agents/optimize_agent.py` | 四维虚构检测（经历/技能/年限/数字）→ risk level | ✅ |
| GreetingAgent | `agents/optimize_agent.py` | 150字内个性化招呼 | ✅ |
| ATSAnalyzer | `agents/ats_agent.py` | 5维规则 + LLM 双评分 | ✅ |
| InterviewAgent | `agents/interview_agent.py` | 模拟面试 + Question Graph + Session 持久化 | ✅ |
| MatchScorer | `evaluator/scorer.py` | Rule + LLM + SkillGraph 三元评分 | ✅ |
| ReviewerAgent | `agents/reviewer_agent.py` | 二次审核 + 低质量过滤 | ✅ |
| PlannerAgent | `agents/planner.py` | 10任务 DAG + SharedContext + Reflection 回退重优化 | ✅ |
| JudgeAgent | `agents/judge_agent.py` | 多维度评分（5维）+ passed 判定 | ✅ |
| CriticAgent | `agents/judge_agent.py` | 具体修改建议（非笼统反馈） | ✅ |

---

## CLI 命令

```bash
python run.py init -f 简历.md        # 📝 录入画像
python run.py discover                # 🎯 5方向推荐
python run.py optimize -d 1           # ✨ 优化简历+ATS+招呼
python run.py interview --company 腾讯 # 💬 模拟面试
python run.py dashboard               # 📊 可视化看板（浏览器）
python run.py auto -f 简历.md         # 🚀 一键全流程
```

---

## 数据资产

| 资产 | 位置 | 规模 |
|------|------|------|
| Resume KB | `knowledge/resume_kb/` | 50+ 真实源 / FAISS索引 / Hybrid Search |
| 评测数据集 | `evaluation/datasets/` | 10 JD-Resume 对 / 5行业 |
| Company KB | `knowledge/company_kb.py` | 7天 TTL 缓存 |
| SkillGraph | `knowledge/graph.json` | 30+ 技能节点 / 别名 / 距离算法 |
| Experiment Center | `experiments/center.py` | A/B 对比 / 网格搜索 / best_config |
| Interview Sessions | `knowledge/interview/` | Session JSON 持久化 |

---

## 核心工作流

### Reflection Workflow
```
Optimize → QA 审查 → risk=high? → 回退重优化 → 最多3轮 → 达标或超限
```

### SearchPipeline
```
采集 → 去重 → Embedding预筛 → Rule+KGraph+LLM三元评分 → TopK排序
```

### 自动迁移（JSON → SQLite）
```
首次运行 get_repo() → 检测 JSON 有数据 + SQLite 为空 → 自动迁移
```

---

## 技术注意事项

### Python 版本
- **开发环境**: Python 3.7（Windows Anaconda）
- **目标环境**: Python 3.11+（CI 使用）
- Python 3.7 的 `list[str]` 语法不兼容，核心代码用 `from __future__ import annotations` 延迟求值

### DeepSeek API
- 客户端: httpx 直连（不用 openai SDK，兼容性更好）
- JSON mode: `response_format={"type": "json_object"}` + Prompt 引导
- Embedding: DeepSeek 无公开 Embedding API → Resume KB 用 TF-IDF fallback
- 成本: 全流程约 $0.002（~¥0.015）

### 网络限制
- GitHub 境外访问需代理（`http://127.0.0.1:7890`）
- 海外简历模板站大多超时
- 可访问: 超级简历 WonderCV, 牛客网, DeepSeek API

---

## 已知限制与待办

| 问题 | 影响 | 优先级 |
|------|------|:--:|
| BOSS直聘/拉勾反爬 | 爬虫不可用，需半自动模式 | ⭐⭐⭐ |
| DeepSeek 无 Embedding API | Resume KB 用 TF-IDF，精度有限 | ⭐⭐⭐ |
| Python 3.7 兼容性 hack | 代码有多处 `from __future__` 和 `typing.Union` | ⭐⭐ |
| Playwright asyncio 在 3.7 不可用 | 改用 agent-browser + 同步 Playwright API | ⭐⭐ |
| 知乎/小红书/脉脉反爬 | 简历搜集源受限 | ⭐ |
| CI mypy 严格模式关闭 | 类型检查覆盖面受限 | ⭐ |

---

## 后续建议方向

1. **WebUI**: FastAPI 单文件服务器 + 现有 Jinja2 模板
2. **RAG 增强**: 对接真正的 Embedding API（OpenAI/本地模型）
3. **半自动投递**: agent-browser + 用户手动验证码 → 自动填表
4. **更多简历源**: 突破反爬获取更多真实简历模板
5. **多格式导出**: Markdown/LaTeX/JSON 简历导出

---

## 相关文件索引

| 文件 | 用途 |
|------|------|
| `run.py` | CLI 入口（所有命令） |
| `src/agents/` | 13 个 Agent |
| `src/workflow/` | Planner + Reflection + SharedContext + Orchestrator |
| `src/llm/` | DeepSeek 客户端 + Router + RetryPolicy + CostMonitor |
| `src/domain/rules.py` | ResumeDomain / MatchingDomain / QADomain |
| `src/repository/` | store.py (JSON) + sqlite_store.py (SQLite) |
| `src/models/schemas.py` | Pydantic 数据模型（全部 10 个） |
| `src/evaluator/` | MatchScorer + SearchPipeline |
| `src/exporter/` | ResumeRenderer (HTML) + DashboardBuilder |
| `src/skill_graph/graph.py` | 技能图谱（加载 graph.json） |
| `src/utils/` | Memory + Registry(Prompt/Cache/Plugin/EventBus) + Logging |
| `knowledge/resume_kb.py` | 简历知识库（FAISS + Hybrid Search） |
| `knowledge/company_kb.py` | 公司知识库（7天缓存） |
| `knowledge/graph.json` | 技能图谱定义 |
| `prompts/` | 6 个 Prompt 模板 |
| `templates/` | 3 个 HTML 模板（简历×2 + Dashboard） |
| `evaluation/` | 评测框架 + 数据集 + Benchmark |
| `experiments/` | 实验中心（A/B 对比） |
| `tests/` | 26 个单元测试 |
| `semi_auto.py` | 半自动爬虫（agent-browser） |
| `collect_web.py` | 网上简历搜集 |
| `rebuild_kb.py` | KB 重建脚本 |
| `.github/workflows/ci.yml` | GitHub Actions CI |
| `pyproject.toml` | 项目配置（ruff + mypy + pytest） |

---

*文档最后更新: 2024-07-23 · Job Hunter V3*
