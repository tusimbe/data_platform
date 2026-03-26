# src/main.py
from fastapi import FastAPI

from src.api.errors import register_error_handlers
from src.api.routes.connectors import router as connectors_router
from src.api.routes.health import router as health_router
from src.api.routes.sync_tasks import router as sync_tasks_router
from src.api.routes.sync_logs import router as sync_logs_router
from src.api.routes.push import router as push_router
from src.api.routes.data import router as data_router

app = FastAPI(title="数据中台", version="0.1.0")

# 注册统一错误处理
register_error_handlers(app)

# 注册路由 — 健康检查免认证
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(connectors_router, prefix="/api/v1", tags=["connectors"])
app.include_router(sync_tasks_router, prefix="/api/v1", tags=["sync"])
app.include_router(sync_logs_router, prefix="/api/v1", tags=["sync"])
app.include_router(push_router, prefix="/api/v1", tags=["push"])
app.include_router(data_router, prefix="/api/v1", tags=["data"])


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
