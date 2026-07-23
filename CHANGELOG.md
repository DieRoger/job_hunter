# Changelog

## V3.0 (2024-07)

### 核心架构
- 四层架构：CLI → Service → Agent → Domain
- SharedContext 统一数据总线
- PlannerAgent DAG 调度 + Reflection 回路
- 18 个异常类全覆盖，RetryPolicy 指数退避+熔断器

### Agent 层（10个）
- ResumeAgent: 简历解析(三格式) → 结构化画像
- CareerAgent: 5方向推荐 + 学习路径 + 项目建议 + 时间线
- JDAnalysisAgent: JD 硬技能/软技能/加分项提取
- SearchAgent: 多平台搜索抽象基类
- ResumeOptimizeAgent: 逐JD定制 + RAG Few-shot
- QAAgent: 4维虚构检测 → risk level
- GreetingAgent: 150字内个性化招呼
- ATSAnalyzer: 5维规则 + LLM 双评分
- InterviewAgent: Question Graph + InterviewSession
- MatchScorer: Rule + LLM + SkillGraph 三元评分
- ReviewerAgent: 二次审核 + 低质量过滤
- PlannerAgent: 10任务 DAG + SharedContext

### 基础设施
- PromptRegistry: 自动加载 + JSON Schema 绑定
- CacheManager + PluginManager + EventBus
- CostMonitor: Token/耗时/成本实时统计
- SkillGraph: 30+节点树形结构 + 别名匹配 + 距离算法
- JSON + SQLite 双 Repository
- UserMemory: 跨会话持久化 + 投递/面试/Offer 跟踪

### 数据资产
- Resume KB: 50+真实源 / 181 chunks / FAISS索引 / Hybrid Search
- 评测数据集: 10 JD-Resume 对 / 5行业
- Company KB: 7天TTL 缓存
- Experiment Center: A/B对比 + 网格搜索 + best_config

### 产品层
- Typer+Rich CLI（9命令）
- Dashboard 单页应用（Chart.js + 暗色主题 + 4Tab）
- HTML简历导出（2套模板）
- agent-browser 半自动爬虫

### 质量
- 26 个核心单元测试（5层覆盖）
- Evaluation Framework: ATS/Keyword Recall/Judge 三元评测
- Benchmark: 一键跑分 + 对比报告
- .gitignore + MIT License + GitHub Actions CI

---

## 更早版本

### V2.0 (之前)
- 初始项目骨架
- 基础 LLM 抽象层
- 基础配置中心
