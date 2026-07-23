"""
统一异常体系 — 全链路错误码，所有异常继承 JobHunterError
"""

from __future__ import annotations

from typing import Any


class JobHunterError(Exception):
    """Job Hunter 基础异常，所有自定义异常继承此类"""

    code: str = "JH0000"
    message: str = "未知错误"

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ─── LLM 层异常 ───────────────────────────────────────────

class LLMError(JobHunterError):
    """LLM 调用基础异常"""
    code = "JH1001"

class LLMAuthError(LLMError):
    """认证失败（API Key 无效/过期）"""
    code = "JH1002"

class LLMRateLimitError(LLMError):
    """请求频率超限"""
    code = "JH1003"

class LLMTimeoutError(LLMError):
    """请求超时"""
    code = "JH1004"

class LLMInvalidResponseError(LLMError):
    """响应格式无效 / JSON 解析失败"""
    code = "JH1005"

class LLMContextOverflowError(LLMError):
    """上下文超长"""
    code = "JH1006"


# ─── 爬虫层异常 ───────────────────────────────────────────

class CrawlerError(JobHunterError):
    """爬虫基础异常"""
    code = "JH2001"

class CrawlerAuthError(CrawlerError):
    """平台登录失败"""
    code = "JH2002"

class CrawlerBlockedError(CrawlerError):
    """被反爬封锁"""
    code = "JH2003"

class CrawlerParseError(CrawlerError):
    """页面解析失败"""
    code = "JH2004"

class CrawlerCaptchaError(CrawlerError):
    """遇到验证码"""
    code = "JH2005"


# ─── 验证层异常 ───────────────────────────────────────────

class ValidationError(JobHunterError):
    """数据校验基础异常"""
    code = "JH3001"

class ProfileValidationError(ValidationError):
    """用户画像校验失败"""
    code = "JH3002"

class ResumeValidationError(ValidationError):
    """简历校验失败"""
    code = "JH3003"

class JDValidationError(ValidationError):
    """JD 校验失败"""
    code = "JH3004"


# ─── 熔断与重试异常 ───────────────────────────────────────

class CircuitBreakerError(JobHunterError):
    """熔断器打开"""
    code = "JH4001"

class MaxRetryExceededError(JobHunterError):
    """超过最大重试次数"""
    code = "JH4002"


# ─── 缓存与存储异常 ───────────────────────────────────────

class CacheError(JobHunterError):
    """缓存操作失败"""
    code = "JH5001"

class RepositoryError(JobHunterError):
    """存储层操作失败"""
    code = "JH5002"


# ─── 配置异常 ─────────────────────────────────────────────

class ConfigurationError(JobHunterError):
    """配置错误"""
    code = "JH6001"


# ─── 工作流异常 ───────────────────────────────────────────

class WorkflowError(JobHunterError):
    """工作流执行错误"""
    code = "JH7001"

class WorkflowStateError(WorkflowError):
    """工作流状态错误（如断点恢复时状态不一致）"""
    code = "JH7002"
