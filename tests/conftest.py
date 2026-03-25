import src.models  # noqa: F401

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base


@pytest.fixture(scope="session")
def engine():
    """使用 SQLite 内存数据库做测试"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(engine):
    """每个测试一个独立事务，测试后回滚"""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
