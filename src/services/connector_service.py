# src/services/connector_service.py
"""连接器管理服务：CRUD + 凭证加密 + 软删除级联"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.connectors.base import connector_registry
from src.core.config import get_settings
from src.core.security import encrypt_value
from src.models.connector import Connector
from src.models.sync import SyncTask


def _encrypt_auth_config(auth_config: dict) -> dict:
    """加密 auth_config，返回包含密文的字典"""
    settings = get_settings()
    if not auth_config:
        return auth_config
    if not settings.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY must be configured to store connector credentials")
    encrypted = encrypt_value(json.dumps(auth_config), settings.ENCRYPTION_KEY)
    return {"_encrypted": encrypted}


def list_connectors(session: Session, params: PaginationParams) -> dict:
    """分页列出所有连接器"""
    query = session.query(Connector).order_by(Connector.id)
    return paginate(query, params)


def get_connector(session: Session, connector_id: int) -> Connector:
    """按 ID 获取连接器，不存在则 404"""
    connector = session.query(Connector).filter_by(id=connector_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector with id {connector_id} not found")
    return connector


def create_connector(session: Session, data: dict) -> Connector:
    """创建连接器，加密凭证"""
    # 验证 connector_type
    valid_types = connector_registry.list_types()
    if data["connector_type"] not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid connector type: {data['connector_type']}. Valid: {valid_types}",
        )

    # 检查名称唯一性
    existing = session.query(Connector).filter_by(name=data["name"]).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Connector name '{data['name']}' already exists"
        )

    # 加密 auth_config
    auth_config = _encrypt_auth_config(data.get("auth_config", {}))

    connector = Connector(
        name=data["name"],
        connector_type=data["connector_type"],
        base_url=data["base_url"],
        auth_config=auth_config,
        description=data.get("description"),
    )
    session.add(connector)
    session.flush()
    return connector


def update_connector(session: Session, connector_id: int, data: dict) -> Connector:
    """更新连接器配置"""
    connector = get_connector(session, connector_id)

    # 如果更新 connector_type，验证
    if "connector_type" in data and data["connector_type"] is not None:
        valid_types = connector_registry.list_types()
        if data["connector_type"] not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid connector type: {data['connector_type']}. Valid: {valid_types}",
            )

    # 如果更新 name，检查唯一性
    if "name" in data and data["name"] is not None and data["name"] != connector.name:
        existing = session.query(Connector).filter_by(name=data["name"]).first()
        if existing:
            raise HTTPException(
                status_code=409, detail=f"Connector name '{data['name']}' already exists"
            )

    for key, value in data.items():
        if value is None:
            continue
        if key == "auth_config":
            setattr(connector, key, _encrypt_auth_config(value))
        elif hasattr(connector, key):
            setattr(connector, key, value)

    session.flush()
    return connector


def delete_connector(session: Session, connector_id: int) -> None:
    """软删除：禁用连接器 + 级联禁用关联同步任务"""
    connector = get_connector(session, connector_id)
    connector.enabled = False

    # 级联禁用关联的同步任务
    sync_tasks = session.query(SyncTask).filter_by(connector_id=connector_id).all()
    for task in sync_tasks:
        task.enabled = False

    session.flush()


def connector_to_response(connector: Connector) -> dict:
    """将 Connector ORM 对象转为响应字典（隐藏 auth_config）"""
    return {
        "id": connector.id,
        "name": connector.name,
        "connector_type": connector.connector_type,
        "base_url": connector.base_url,
        "has_auth_config": bool(connector.auth_config),
        "enabled": connector.enabled,
        "description": connector.description,
        "created_at": connector.created_at,
        "updated_at": connector.updated_at,
    }
