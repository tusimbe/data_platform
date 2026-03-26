# src/api/routes/data.py
"""统一数据 + 原始数据查询 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams, paginate
from src.models.connector import Connector
from src.models.raw_data import RawData
from src.models.unified import (
    UnifiedCustomer, UnifiedOrder, UnifiedProduct,
    UnifiedInventory, UnifiedProject, UnifiedContact,
)

router = APIRouter(dependencies=[Depends(get_current_api_key)])

# 实体路由映射
ENTITY_REGISTRY: dict[str, type] = {
    "customers": UnifiedCustomer,
    "orders": UnifiedOrder,
    "products": UnifiedProduct,
    "inventory": UnifiedInventory,
    "projects": UnifiedProject,
    "contacts": UnifiedContact,
}

# 分页/排序相关的保留参数名，不当作过滤条件
RESERVED_PARAMS = {"page", "page_size", "sort_by", "sort_order"}


def _get_model(entity: str):
    model = ENTITY_REGISTRY.get(entity)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown entity: {entity}. Valid: {list(ENTITY_REGISTRY.keys())}",
        )
    return model


@router.get("/data/{entity}")
def list_unified_data(
    entity: str,
    request: Request,
    params: PaginationParams = Depends(),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_db),
):
    model = _get_model(entity)
    query = session.query(model)

    # 动态过滤
    valid_columns = {c.name for c in model.__table__.columns}
    for key, value in request.query_params.items():
        if key in RESERVED_PARAMS:
            continue
        if key not in valid_columns:
            raise HTTPException(status_code=400, detail=f"Invalid filter column: {key}")
        query = query.filter(getattr(model, key) == value)

    # 排序
    if sort_by not in valid_columns:
        raise HTTPException(status_code=400, detail=f"Invalid sort column: {sort_by}")
    order_col = getattr(model, sort_by)
    query = query.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())

    result = paginate(query, params)
    # 将 ORM 对象序列化为字典
    result["items"] = [
        {c.name: getattr(row, c.name) for c in model.__table__.columns}
        for row in result["items"]
    ]
    return result


@router.get("/data/{entity}/{record_id}")
def get_unified_record(
    entity: str,
    record_id: int,
    session: Session = Depends(get_db),
):
    model = _get_model(entity)
    record = session.query(model).filter_by(id=record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"{entity} record with id {record_id} not found")
    return {c.name: getattr(record, c.name) for c in model.__table__.columns}


@router.get("/raw/{connector_type}/{entity}")
def list_raw_data(
    connector_type: str,
    entity: str,
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    # 查找匹配 connector_type 的所有 connector_id
    connector_ids = [
        c.id for c in
        session.query(Connector.id).filter_by(connector_type=connector_type).all()
    ]
    if not connector_ids:
        raise HTTPException(status_code=404, detail=f"No connectors found for type: {connector_type}")

    query = (
        session.query(RawData)
        .filter(RawData.connector_id.in_(connector_ids))
        .filter(RawData.entity == entity)
        .order_by(RawData.synced_at.desc())
    )
    result = paginate(query, params)
    result["items"] = [
        {
            "id": row.id,
            "connector_id": row.connector_id,
            "entity": row.entity,
            "external_id": row.external_id,
            "data": row.data,
            "synced_at": row.synced_at,
        }
        for row in result["items"]
    ]
    return result
