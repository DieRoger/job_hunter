"""
配置中心 — 统一加载 default.yaml / model.yaml / crawler.yaml / resume.yaml
支持环境变量覆盖（JOB_HUNTER_* 前缀）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

# ─── 子配置模型 ───────────────────────────────────────────

class AppConfig(BaseModel):
    name: str = "Job Hunter"
    version: str = "0.1.0"
    data_dir: str = "~/.job-hunter"


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    default_model: str = "deepseek-chat"
    reasoner_model: str = "deepseek-reasoner"
    embedding_model: str = "deepseek-embed"
    temperature: float = 0.2
    max_tokens: int = 4096
    request_timeout: int = 60


class DiscoverConfig(BaseModel):
    top_n_directions: int = 5
    temperature: float = 0.4


class SearchConfig(BaseModel):
    top_n_jobs_per_direction: int = 10
    platforms: list[str] = ["boss", "lagou"]


class MatchingWeights(BaseModel):
    rule_weight: float = 0.4
    llm_weight: float = 0.35
    skill_graph_weight: float = 0.25


class MatchingConfig(BaseModel):
    rule_weight: float = 0.4
    llm_weight: float = 0.35
    skill_graph_weight: float = 0.25
    min_score_threshold: int = 50


class HardConstraints(BaseModel):
    forbid_fabricated_experience: bool = True
    forbid_fake_skills: bool = True
    forbid_exaggerated_years: bool = True
    forbid_fake_projects: bool = True


class OptimizeConfig(BaseModel):
    max_skill_inflation: float = 0.15
    hard_constraints: HardConstraints = HardConstraints()


class QAConfig(BaseModel):
    risk_threshold_reject: str = "high"
    risk_threshold_warn: str = "medium"


class ExportConfig(BaseModel):
    template: str = "professional"
    format: str = "pdf"
    output_dir: str = "export"


class DefaultConfig(BaseModel):
    app: AppConfig = AppConfig()
    llm: LLMConfig = LLMConfig()
    discover: DiscoverConfig = DiscoverConfig()
    search: SearchConfig = SearchConfig()
    matching: MatchingConfig = MatchingConfig()
    optimize: OptimizeConfig = OptimizeConfig()
    qa: QAConfig = QAConfig()
    export: ExportConfig = ExportConfig()


# ─── 模型配置 ─────────────────────────────────────────────

class ModelInfo(BaseModel):
    max_tokens: int = 4096
    supports_json_mode: bool = True
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    models: dict[str, ModelInfo]
    default_model: str
    reasoner_model: str | None = None


class RouterRule(BaseModel):
    task_pattern: str
    model: str  # "default" | "reasoner"


class RouterConfig(BaseModel):
    rules: list[RouterRule] = []
    embedding_provider: str = "deepseek"
    embedding_model: str = "deepseek-embed"


class ModelConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    router: RouterConfig


# ─── 爬虫配置 ─────────────────────────────────────────────

class PlatformCrawlerConfig(BaseModel):
    name: str
    base_url: str
    search_url: str
    enabled: bool = True
    request_interval: list[int] = [3, 8]
    max_retries: int = 3
    page_timeout: int = 30


class BrowserConfig(BaseModel):
    headless: bool = True
    viewport: list[int] = [1920, 1080]
    user_agent: str = ""
    locale: str = "zh-CN"
    stealth_mode: bool = True


class AntiDetectConfig(BaseModel):
    random_delay: bool = True
    simulate_human_scroll: bool = True
    max_concurrent_sessions: int = 2


class CrawlerConfig(BaseModel):
    platforms: dict[str, PlatformCrawlerConfig]
    browser: BrowserConfig
    anti_detect: AntiDetectConfig


# ─── 简历模板配置 ─────────────────────────────────────────

class TemplateColors(BaseModel):
    primary: str = "#1a1a2e"
    accent: str = "#16213e"
    text: str = "#333333"


class ResumeTemplate(BaseModel):
    name: str
    html: str
    fonts: list[str] = []
    colors: TemplateColors = TemplateColors()


class OptimizationWeights(BaseModel):
    skill_highlight: float = 0.35
    project_reorder: float = 0.25
    description_rewrite: float = 0.25
    format_ats: float = 0.15


class OptimizationSettings(BaseModel):
    weights: OptimizationWeights = OptimizationWeights()


class SectionsOrder(BaseModel):
    order: list[str] = ["personal_info", "summary", "skills", "experience", "projects", "education", "certifications"]


class ResumeConfig(BaseModel):
    templates: dict[str, ResumeTemplate]
    optimization: OptimizationSettings
    sections: SectionsOrder


# ─── 配置加载器 ───────────────────────────────────────────

class ConfigLoader:
    """统一配置加载器，单例模式"""

    _instance: ConfigLoader | None = None
    _config_dir: Path = Path()  # placeholder, 在 __init__ 中被覆盖

    def __init__(self, config_dir: str | Path | None = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        self._config_dir = Path(config_dir)
        self._cache: dict[str, Any] = {}

    @classmethod
    def get_instance(cls, config_dir: str | Path | None = None) -> ConfigLoader:
        if cls._instance is None:
            cls._instance = cls(config_dir)
        return cls._instance

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        if filename in self._cache:
            return self._cache[filename]
        filepath = self._config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"配置文件不存在: {filepath}")
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self._cache[filename] = data
        return data

    @property
    def default(self) -> DefaultConfig:
        data = self._load_yaml("default.yaml")
        return DefaultConfig(**data)

    @property
    def model(self) -> ModelConfig:
        data = self._load_yaml("model.yaml")
        return ModelConfig(**data)

    @property
    def crawler(self) -> CrawlerConfig:
        data = self._load_yaml("crawler.yaml")
        return CrawlerConfig(**data)

    @property
    def resume(self) -> ResumeConfig:
        data = self._load_yaml("resume.yaml")
        return ResumeConfig(**data)


# 模块级快捷访问
_config = ConfigLoader.get_instance()

default_config = _config.default
model_config = _config.model
crawler_config = _config.crawler
resume_config = _config.resume
