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


from src.core.security import encrypt_value, decrypt_value


def test_encrypt_decrypt_roundtrip():
    """加密后解密应还原原始值"""
    key = "test-secret-key-for-encryption!!"  # 32 bytes
    original = "my_secret_password_123"
    encrypted = encrypt_value(original, key)
    assert encrypted != original
    decrypted = decrypt_value(encrypted, key)
    assert decrypted == original


def test_encrypt_produces_different_output():
    """同一明文多次加密应产生不同密文（因 IV 不同）"""
    key = "test-secret-key-for-encryption!!"
    val = "same_value"
    e1 = encrypt_value(val, key)
    e2 = encrypt_value(val, key)
    assert e1 != e2  # Fernet 使用随机 IV
