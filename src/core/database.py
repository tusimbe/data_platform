import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_engine = None
_SessionLocal = None
_init_lock = threading.Lock()


def init_db(database_url: str, echo: bool = False):
    global _engine, _SessionLocal
    with _init_lock:
        if _engine is not None:
            return
        _engine = create_engine(database_url, echo=echo)
        _SessionLocal = sessionmaker(bind=_engine)


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session_local():
    """返回 SessionLocal 工厂，供非 FastAPI 环境使用（Celery task/scheduler）。
    如果 DB 未初始化，自动初始化。"""
    global _engine, _SessionLocal
    should_init = False
    if _SessionLocal is None:
        with _init_lock:
            if _SessionLocal is None:
                should_init = True
    if should_init:
        from src.core.config import get_settings

        settings = get_settings()
        init_db(settings.DATABASE_URL, settings.DATABASE_ECHO)
    return _SessionLocal
