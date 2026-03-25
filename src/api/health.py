from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """平台健康检查"""
    # 简化版：后续 Task 会添加 DB/Redis/Celery 检查
    return {
        "status": "healthy",
        "components": {
            "database": "not_configured",
            "redis": "not_configured",
            "celery": "not_configured",
        },
    }
