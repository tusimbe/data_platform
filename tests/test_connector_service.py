import pytest
from unittest.mock import patch, MagicMock

from src.services.connector_service import _encrypt_auth_config


class TestEncryptAuthConfig:
    def test_empty_auth_config_returns_as_is(self):
        result = _encrypt_auth_config({})
        assert result == {}

    def test_none_auth_config_returns_as_is(self):
        result = _encrypt_auth_config(None)
        assert result is None

    def test_empty_encryption_key_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.ENCRYPTION_KEY = ""
        with patch("src.services.connector_service.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="ENCRYPTION_KEY must be configured"):
                _encrypt_auth_config({"app_id": "test", "secret": "val"})

    def test_valid_encryption_returns_encrypted_dict(self):
        result = _encrypt_auth_config({"app_id": "test123"})
        assert "_encrypted" in result
        assert isinstance(result["_encrypted"], str)
