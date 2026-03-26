# src/services/push_service.py
"""数据推送服务：连接器实例化 + 连接管理 + 推送执行"""
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.connectors.base import connector_registry, ConnectorError, PushResult
from src.core.config import get_settings
from src.core.security import decrypt_value
from src.models.connector import Connector


def execute_push(
    connector_type: str,
    entity: str,
    records: list[dict],
    session: Session,
) -> PushResult:
    """
    执行数据推送：
    1. 查 DB 找 enabled 的连接器
    2. 实例化连接器
    3. connect → push → disconnect
    """
    # 查找启用的连接器
    connector_model = (
        session.query(Connector)
        .filter_by(connector_type=connector_type, enabled=True)
        .first()
    )
    if not connector_model:
        raise HTTPException(
            status_code=404,
            detail=f"No enabled connector found for type: {connector_type}",
        )

    # 实例化连接器
    connector_class = connector_registry.get(connector_type)
    auth_config = connector_model.auth_config

    # 解密凭证
    settings = get_settings()
    if isinstance(auth_config, dict) and "_encrypted" in auth_config:
        decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
        auth_config = json.loads(decrypted)

    config = {
        "base_url": connector_model.base_url,
        "auth_config": auth_config,
    }
    connector = connector_class(config)

    try:
        connector.connect()
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=f"Connector unavailable: {str(e)}")

    try:
        result = connector.push(entity, records)
        return result
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=f"Push failed: {str(e)}")
    finally:
        try:
            connector.disconnect()
        except Exception:
            pass
