import os

# 设置测试环境变量 — 必须在导入 app 之前
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing")

import src.models  # noqa: F401

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from src.models.base import Base


@pytest.fixture(scope="session")
def engine():
    """使用 SQLite 内存数据库做测试"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(engine):
    """每个测试用 connection-level transaction 包裹，确保测试隔离。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient，覆盖 DB session 依赖"""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.api.deps import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_headers():
    """带有效 API Key 的请求头"""
    return {"Authorization": "Bearer test-api-key"}
