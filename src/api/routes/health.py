# src/api/routes/health.py
"""增强版健康检查端点"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_db

router = APIRouter()


@router.get("/health")
def health_check(session: Session = Depends(get_db)):
    """
    平台健康检查 — 免认证。
    检查: database, redis (not_configured), celery (not_configured)
    """
    components = {}

    # 数据库检查
    try:
        start = time.time()
        session.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 2)
        components["database"] = {"status": "healthy", "latency_ms": latency_ms}
    except Exception as e:
        components["database"] = {"status": "unhealthy", "error": str(e)}

    # Redis — 当前未配置
    components["redis"] = {"status": "not_configured"}

    # Celery — 当前未配置
    components["celery"] = {"status": "not_configured"}

    # 计算 overall status
    db_status = components["database"]["status"]
    if db_status == "unhealthy":
        overall = "unhealthy"
    elif any(
        c["status"] == "unhealthy"
        for key, c in components.items()
        if key != "database"
    ):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "components": components,
        "version": "0.1.0",
    }
