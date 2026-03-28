# src/main.py
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from src.api.errors import register_error_handlers
from src.api.routes.connectors import router as connectors_router
from src.api.routes.health import router as health_router
from src.api.routes.sync_tasks import router as sync_tasks_router
from src.api.routes.sync_logs import router as sync_logs_router
from src.api.routes.push import router as push_router
from src.api.routes.data import router as data_router
from src.api.routes.field_mappings import router as field_mappings_router
from src.api.routes.entity_schemas import router as entity_schemas_router
from src.api.routes.flows import router as flows_router
from src.core.config import get_settings
from src.core.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.DATABASE_URL, settings.DATABASE_ECHO)
    logger.info("Database initialized")
    yield


app = FastAPI(title="数据中台", version="0.1.0", lifespan=lifespan)

# 注册统一错误处理
register_error_handlers(app)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 — 健康检查免认证
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(connectors_router, prefix="/api/v1", tags=["connectors"])
app.include_router(sync_tasks_router, prefix="/api/v1", tags=["sync"])
app.include_router(sync_logs_router, prefix="/api/v1", tags=["sync"])
app.include_router(push_router, prefix="/api/v1", tags=["push"])
app.include_router(data_router, prefix="/api/v1", tags=["data"])
app.include_router(field_mappings_router, prefix="/api/v1", tags=["field-mappings"])
app.include_router(entity_schemas_router, prefix="/api/v1", tags=["entity-schemas"])
app.include_router(flows_router, prefix="/api/v1", tags=["flows"])

# SPA fallback — 当 frontend/dist 目录存在时，挂载静态文件服务
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_frontend_dir = os.path.normpath(_frontend_dir)


class _SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for SPA routing."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                # SPA fallback: return index.html for any unknown path
                return await super().get_response("index.html", scope)
            raise


if os.path.isdir(_frontend_dir):
    app.mount("/", _SPAStaticFiles(directory=_frontend_dir, html=True), name="spa")
else:

    @app.get("/")
    def root():
        return {"name": "数据中台", "version": "0.1.0"}
