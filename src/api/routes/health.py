# src/api/routes/health.py
"""增强版健康检查端点"""

import time

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_current_api_key, get_db
from src.core.config import get_settings

router = APIRouter()


def _check_redis() -> dict:
    """检查 Redis 连接状态"""
    r = None
    try:
        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL)
        start = time.time()
        r.ping()
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception:
        return {"status": "unhealthy", "error": "Redis connection failed"}
    finally:
        if r is not None:
            r.close()


def _check_celery() -> dict:
    """检查 Celery worker 是否在线"""
    try:
        from src.core.celery_app import celery_app

        start = time.time()
        response = celery_app.control.ping(timeout=2.0)
        latency_ms = round((time.time() - start) * 1000, 2)
        if response:
            return {"status": "healthy", "latency_ms": latency_ms}
        else:
            return {"status": "unhealthy", "error": "No workers available"}
    except Exception:
        return {"status": "unhealthy", "error": "Celery check failed"}


def _build_health_response(session: Session, include_details: bool) -> dict:
    components = {}

    # 数据库检查
    try:
        start = time.time()
        session.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 2)
        components["database"] = {"status": "healthy", "latency_ms": latency_ms}
    except Exception:
        components["database"] = {
            "status": "unhealthy",
            "error": "Database connection failed",
        }

    # Redis 检查
    components["redis"] = _check_redis()

    # Celery 检查
    components["celery"] = _check_celery()

    # 计算 overall status
    db_status = components["database"]["status"]
    if db_status == "unhealthy":
        overall = "unhealthy"
    elif any(c["status"] == "unhealthy" for key, c in components.items() if key != "database"):
        overall = "degraded"
    else:
        overall = "healthy"

    if not include_details:
        return {"status": overall}

    return {
        "status": overall,
        "components": components,
        "version": "0.1.0",
    }


@router.get("/health")
def health_check(session: Session = Depends(get_db)):
    """
    平台健康检查 — 免认证。
    检查: database, redis, celery
    """
    return _build_health_response(session=session, include_details=False)


@router.get("/health/detail")
def health_detail(
    session: Session = Depends(get_db),
    _: str = Depends(get_current_api_key),
):
    return _build_health_response(session=session, include_details=True)
