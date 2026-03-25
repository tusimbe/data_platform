import os
from unittest.mock import patch


def test_default_config():
    """默认配置应有合理的默认值"""
    from src.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert settings.APP_NAME == "数据中台"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DATABASE_URL == "postgresql://u:p@localhost/db"


def test_config_from_env():
    """配置应支持从环境变量读取"""
    with patch.dict(os.environ, {
        "DATABASE_URL": "postgresql://test:test@db/test",
        "REDIS_URL": "redis://redis:6379/0",
        "APP_NAME": "测试中台",
    }):
        from importlib import reload
        import src.core.config as config_mod
        reload(config_mod)
        settings = config_mod.Settings()
        assert settings.APP_NAME == "测试中台"
        assert settings.DATABASE_URL == "postgresql://test:test@db/test"
