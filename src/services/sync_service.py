# src/services/sync_service.py
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.connectors.base import BaseConnector
from src.services.field_mapping_service import FieldMappingService

logger = logging.getLogger(__name__)


class SyncExecutor:
    """同步执行器：编排拉取/推送的三阶段流程"""

    def __init__(self):
        self._mapping_service = FieldMappingService()

    # --- 拉取流程 ---

    def pull_phase(
        self,
        connector: BaseConnector,
        entity: str,
        since: datetime | None = None,
    ) -> list[dict]:
        """阶段1：从外部系统拉取原始数据"""
        return connector.pull(entity=entity, since=since, filters=None)

    def transform_phase(
        self,
        raw_records: list[dict],
        mappings: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """阶段2：应用字段映射转换数据。返回 (成功列表, 错误列表)"""
        transformed = []
        errors = []

        for record in raw_records:
            try:
                mapped = self._mapping_service.apply_mappings(record, mappings)
                mapped["_raw"] = record  # 保留原始数据引用
                transformed.append(mapped)
            except Exception as e:
                errors.append({
                    "record": record,
                    "error": str(e),
                })

        return transformed, errors

    def store_phase(
        self,
        connector_id: int,
        entity: str,
        raw_records: list[dict],
        transformed_records: list[dict],
        target_table: str,
        session: Session,
        sync_log_id: int | None = None,
    ) -> int:
        """阶段3：存储原始数据到 raw_data + 更新插入统一表。返回存储成功条数"""
        from src.models.raw_data import RawData

        stored = 0
        for raw in raw_records:
            external_id = self._extract_external_id(raw, entity)
            if not external_id:
                continue

            # 更新插入 raw_data
            existing = session.query(RawData).filter_by(
                connector_id=connector_id,
                entity=entity,
                external_id=str(external_id),
            ).first()

            if existing:
                existing.data = raw
                existing.synced_at = datetime.now(timezone.utc)
                existing.sync_log_id = sync_log_id
            else:
                raw_data = RawData(
                    connector_id=connector_id,
                    entity=entity,
                    external_id=str(external_id),
                    data=raw,
                    sync_log_id=sync_log_id,
                )
                session.add(raw_data)

            stored += 1

        session.flush()

        # 更新插入统一表
        unified_model = self._get_unified_model(target_table)
        if unified_model is not None:
            # 提前查询 connector_type，避免循环中 N+1 查询
            connector_type = self._connector_type_for_id(connector_id, session)

            for record in transformed_records:
                mapped = {k: v for k, v in record.items() if k != "_raw"}
                raw_ref = record.get("_raw", {})
                ext_id = self._extract_external_id(raw_ref, entity)
                if not ext_id:
                    continue

                existing_unified = session.query(unified_model).filter_by(
                    source_system=connector_type,
                    external_id=str(ext_id),
                ).first()

                if existing_unified:
                    for k, v in mapped.items():
                        if hasattr(existing_unified, k):
                            coerced = self._coerce_value(unified_model, k, v)
                            setattr(existing_unified, k, coerced)
                else:
                    mapped["source_system"] = connector_type
                    mapped["external_id"] = str(ext_id)
                    # 只传统一模型实际拥有的列
                    valid_cols = {c.name for c in unified_model.__table__.columns}
                    filtered = {k: v for k, v in mapped.items() if k in valid_cols}
                    # 类型强制转换
                    filtered = {
                        k: self._coerce_value(unified_model, k, v)
                        for k, v in filtered.items()
                    }
                    session.add(unified_model(**filtered))

            session.flush()

        return stored

    def execute_pull(
        self,
        connector: BaseConnector,
        connector_id: int,
        entity: str,
        target_table: str,
        mappings: list[dict],
        session: Session,
        since: datetime | None = None,
    ) -> dict:
        """执行完整的拉取同步流程"""
        from src.models.sync import SyncLog

        # 阶段1：拉取
        try:
            raw_records = self.pull_phase(connector, entity, since)
        except Exception as e:
            logger.error(f"拉取阶段失败: {e}")
            log = SyncLog(
                sync_task_id=None,
                connector_id=connector_id,
                entity=entity,
                direction="pull",
                status="failure",
                total_records=0,
                success_count=0,
                failure_count=0,
                error_details={"phase": "pull", "error": str(e)},
                finished_at=datetime.now(timezone.utc),
            )
            session.add(log)
            session.flush()
            return {
                "status": "failure",
                "total_records": 0,
                "success_count": 0,
                "failure_count": 0,
                "errors": [{"phase": "pull", "error": str(e)}],
            }

        total = len(raw_records)

        if total == 0:
            # 即使无数据也记录日志
            log = SyncLog(
                sync_task_id=None,
                connector_id=connector_id,
                entity=entity,
                direction="pull",
                status="success",
                total_records=0,
                success_count=0,
                failure_count=0,
                finished_at=datetime.now(timezone.utc),
            )
            session.add(log)
            session.flush()
            return {
                "status": "success",
                "total_records": 0,
                "success_count": 0,
                "failure_count": 0,
                "errors": [],
            }

        # 阶段2：转换
        transformed, errors = self.transform_phase(raw_records, mappings)

        # 创建 sync_log 记录
        log = SyncLog(
            sync_task_id=None,
            connector_id=connector_id,
            entity=entity,
            direction="pull",
            status="running",
            total_records=total,
            success_count=0,
            failure_count=0,
        )
        session.add(log)
        session.flush()

        # 阶段3：存储（raw_data + 统一表）
        try:
            stored = self.store_phase(
                connector_id, entity, raw_records, transformed,
                target_table, session, sync_log_id=log.id,
            )
        except Exception as e:
            logger.error(f"存储阶段失败: {e}")
            log.status = "failure"
            log.failure_count = total
            log.error_details = {"phase": "store", "error": str(e)}
            log.finished_at = datetime.now(timezone.utc)
            session.flush()
            return {
                "status": "failure",
                "total_records": total,
                "success_count": 0,
                "failure_count": total,
                "errors": [{"phase": "store", "error": str(e)}],
            }

        failure_count = len(errors)
        status = "success" if failure_count == 0 else "partial_success"

        # 更新 sync_log — success_count 使用实际存储条数
        log.status = status
        log.success_count = stored
        log.failure_count = failure_count
        log.error_details = {"errors": errors} if errors else None
        log.finished_at = datetime.now(timezone.utc)
        session.flush()

        return {
            "status": status,
            "total_records": total,
            "success_count": stored,
            "failure_count": failure_count,
            "errors": errors,
        }

    @staticmethod
    def _extract_external_id(record: dict, entity: str) -> str | None:
        """尝试从原始记录中提取外部 ID"""
        for key in ["FBillNo", "FNumber", "FID", "id", "Id", "ID"]:
            if key in record:
                return str(record[key])
        return None

    @staticmethod
    def _get_unified_model(target_table: str):
        """根据表名获取统一模型类"""
        from src.models.unified import (
            UnifiedCustomer, UnifiedOrder, UnifiedProduct,
            UnifiedInventory, UnifiedProject, UnifiedContact,
        )
        table_map = {
            "unified_customers": UnifiedCustomer,
            "unified_orders": UnifiedOrder,
            "unified_products": UnifiedProduct,
            "unified_inventory": UnifiedInventory,
            "unified_projects": UnifiedProject,
            "unified_contacts": UnifiedContact,
        }
        return table_map.get(target_table)

    @staticmethod
    def _connector_type_for_id(connector_id: int, session) -> str:
        """根据 connector_id 查询 connector_type"""
        from src.models.connector import Connector
        c = session.query(Connector).filter_by(id=connector_id).first()
        return c.connector_type if c else "unknown"

    @staticmethod
    def _coerce_value(model_class, column_name: str, value):
        """根据模型列类型强制转换值（如字符串日期 → date 对象）"""
        from datetime import date as date_type
        from sqlalchemy import Date, DateTime

        if value is None:
            return value

        table = model_class.__table__
        if column_name not in table.columns:
            return value

        col_type = table.columns[column_name].type

        if isinstance(col_type, Date) and isinstance(value, str):
            # 尝试解析 YYYY-MM-DD 格式的日期字符串
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return value

        if isinstance(col_type, DateTime) and isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value

        return value
