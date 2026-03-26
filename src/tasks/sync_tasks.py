# src/tasks/sync_tasks.py
"""Celery 同步任务定义"""

import json
import logging
from datetime import datetime, timezone

import redis

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.database import get_session_local
from src.core.entity_registry import get_entity_table
from src.core.security import decrypt_value
from src.connectors.base import connector_registry, ConnectorError
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog
from src.services.sync_service import SyncExecutor

logger = logging.getLogger(__name__)
settings = get_settings()
redis_client = redis.from_url(settings.REDIS_URL)


@celery_app.task(
    name="sync.run_sync_task",
    autoretry_for=(ConnectorError, redis.ConnectionError, redis.TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=settings.SYNC_TASK_MAX_RETRIES,
    acks_late=True,
)
def run_sync_task(task_id: int):
    """执行单个 SyncTask 的同步"""
    lock = redis_client.lock(
        name=f"sync_lock:{task_id}",
        timeout=settings.SYNC_LOCK_TIMEOUT,
        blocking=False,
    )

    if not lock.acquire(blocking=False):
        logger.info(f"Task {task_id} already running, skipping")
        return {"status": "skipped", "reason": "already_running"}

    SessionLocal = get_session_local()
    session = SessionLocal()
    sync_log = None
    try:
        # 1. 加载任务和连接器
        task = session.query(SyncTask).filter_by(id=task_id).first()
        if not task or not task.enabled:
            logger.warning(f"Task {task_id} not found or disabled")
            return {"status": "skipped", "reason": "not_found_or_disabled"}

        connector_model = session.query(Connector).filter_by(id=task.connector_id).first()
        if not connector_model or not connector_model.enabled:
            logger.warning(f"Connector for task {task_id} not found or disabled")
            return {"status": "skipped", "reason": "connector_unavailable"}

        # 2. 创建 SyncLog
        sync_log = SyncLog(
            sync_task_id=task.id,
            connector_id=connector_model.id,
            entity=task.entity,
            direction=task.direction,
            status="running",
        )
        session.add(sync_log)
        session.flush()

        # 3. push 方向暂不支持
        if task.direction != "pull":
            sync_log.status = "skipped"
            sync_log.finished_at = datetime.now(timezone.utc)
            session.commit()
            return {"status": "skipped", "reason": "push_not_supported", "task_id": task_id}

        # 4. 实例化连接器
        connector_class = connector_registry.get(connector_model.connector_type)
        auth_config = connector_model.auth_config
        if isinstance(auth_config, dict) and "_encrypted" in auth_config:
            decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
            auth_config = json.loads(decrypted)

        config = {"base_url": connector_model.base_url}
        if isinstance(auth_config, dict):
            config.update(auth_config)
        connector = connector_class(config)

        # 5. 执行同步
        try:
            connector.connect()
            executor = SyncExecutor()
            target_table = get_entity_table(task.entity)

            # Read field mappings from task config
            task_config = task.config or {}
            mappings = task_config.get("mappings", [])

            result = executor.execute_pull(
                connector=connector,
                connector_id=connector_model.id,
                entity=task.entity,
                target_table=target_table,
                mappings=mappings,
                session=session,
                since=task.last_sync_at,
            )

            # 更新状态
            sync_log.status = "success"
            sync_log.total_records = result.get("total_records", 0)
            sync_log.success_count = result.get("success_count", 0)
            sync_log.finished_at = datetime.now(timezone.utc)
            task.last_sync_at = datetime.now(timezone.utc)
        finally:
            try:
                connector.disconnect()
            except Exception:
                pass

        session.commit()
        logger.info(f"Task {task_id} completed: {sync_log.status}")
        return {"status": sync_log.status, "task_id": task_id}

    except ConnectorError:
        # 让 Celery autoretry 处理
        if sync_log:
            sync_log.status = "failed"
            sync_log.finished_at = datetime.now(timezone.utc)
            try:
                session.commit()
            except Exception:
                session.rollback()
        raise
    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        if sync_log:
            sync_log.status = "failed"
            sync_log.error_details = {"error": str(e)}
            sync_log.finished_at = datetime.now(timezone.utc)
        try:
            session.commit()
        except Exception:
            session.rollback()
        return {"status": "failed", "task_id": task_id, "error": str(e)}
    finally:
        session.close()
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass  # 锁已过期
