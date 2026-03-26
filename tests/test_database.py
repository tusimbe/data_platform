import threading
from unittest.mock import patch, MagicMock

import pytest


def test_get_session_local_initializes_on_first_call():
    import src.core.database as db_mod

    original_engine = db_mod._engine
    original_session = db_mod._SessionLocal

    try:
        db_mod._engine = None
        db_mod._SessionLocal = None

        mock_session_local = MagicMock()
        with patch.object(db_mod, "init_db") as mock_init:

            def fake_init(url, echo=False):
                db_mod._SessionLocal = mock_session_local

            mock_init.side_effect = fake_init

            result = db_mod.get_session_local()

            mock_init.assert_called_once()
            assert result is mock_session_local
    finally:
        db_mod._engine = original_engine
        db_mod._SessionLocal = original_session


def test_get_session_local_concurrent_returns_same_session_local():
    import src.core.database as db_mod

    barrier = threading.Barrier(5)
    results = [None] * 5

    def worker(idx):
        barrier.wait()
        results[idx] = db_mod.get_session_local()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(r is results[0] for r in results)


def test_get_session_raises_when_not_initialized():
    import src.core.database as db_mod

    original_session = db_mod._SessionLocal
    try:
        db_mod._SessionLocal = None
        gen = db_mod.get_session()
        with pytest.raises(RuntimeError, match="Database not initialized"):
            next(gen)
    finally:
        db_mod._SessionLocal = original_session
