# src/core/exceptions.py
"""领域异常 — 业务逻辑层使用，与 HTTP 框架解耦"""


class AppError(Exception):
    """应用层异常基类"""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    """资源不存在"""

    pass


class ConflictError(AppError):
    """资源冲突（如名称重复）"""

    pass


class ValidationError(AppError):
    """业务校验失败"""

    pass


class ServiceUnavailableError(AppError):
    """外部服务不可用"""

    pass


class NotImplementedError_(AppError):
    """功能未实现"""

    pass
