# src/api/deps.py
import hmac

from fastapi import HTTPException, Query, Request

from src.core.config import get_settings
from src.core.database import get_session


def get_db():
    """数据库 session 依赖（可在测试中 override）"""
    yield from get_session()


def get_current_api_key(request: Request) -> str:
    """API Key 认证依赖。从 Authorization: Bearer <key> 或 X-API-Key 头提取。"""
    settings = get_settings()

    if not settings.API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured")

    # 尝试 Authorization: Bearer <key>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if hmac.compare_digest(token, settings.API_KEY):
            return token

    # 尝试 X-API-Key
    api_key = request.headers.get("X-API-Key", "")
    if hmac.compare_digest(api_key, settings.API_KEY):
        return api_key

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


class PaginationParams:
    """分页参数依赖"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paginate(query, params: PaginationParams) -> dict:
    """对 SQLAlchemy query 应用分页，返回标准分页响应字典。"""
    total_count = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return {
        "items": items,
        "total_count": total_count,
        "page": params.page,
        "page_size": params.page_size,
    }
