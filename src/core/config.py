from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持环境变量和 .env 文件"""

    APP_NAME: str = "数据中台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str

    # API
    API_V1_PREFIX: str = "/api/v1"
    API_KEY: str = ""

    # 安全
    ENCRYPTION_KEY: str = ""

    # Celery
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # 调度器
    SCHEDULER_SYNC_INTERVAL: int = 15

    # 分布式锁
    SYNC_LOCK_TIMEOUT: int = 3600

    # 任务重试
    SYNC_TASK_MAX_RETRIES: int = 3
    SYNC_TASK_RETRY_BACKOFF: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
