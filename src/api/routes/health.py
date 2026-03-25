# src/api/routes/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """健康检查 — 简化版，Task 7 增强"""
    return {
        "status": "healthy",
        "components": {
            "database": {"status": "not_configured"},
            "redis": {"status": "not_configured"},
            "celery": {"status": "not_configured"},
        },
        "version": "0.1.0",
    }
