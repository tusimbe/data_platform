from src.models.base import Base
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog
from src.models.raw_data import RawData
from src.models.unified import (
    UnifiedCustomer, UnifiedOrder, UnifiedProduct,
    UnifiedInventory, UnifiedProject, UnifiedContact,
)
from src.models.field_mapping import FieldMapping, EntitySchema


def test_base_model_exists():
    """声明式基类应存在且可用"""
    assert Base is not None
    assert hasattr(Base, "metadata")


def test_create_connector(db_session):
    """应能创建连接器配置记录"""
    c = Connector(
        name="测试金蝶ERP",
        connector_type="kingdee_erp",
        base_url="https://api.kingdee.com",
        auth_config={"app_id": "xxx", "app_secret": "yyy"},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    assert c.id is not None
    assert c.connector_type == "kingdee_erp"
    assert c.enabled is True


def test_create_sync_task(db_session):
    """应能创建同步任务"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    task = SyncTask(
        connector_id=c.id,
        entity="sales_order",
        direction="pull",
        cron_expression="0 */2 * * *",
        enabled=True,
    )
    db_session.add(task)
    db_session.flush()
    assert task.id is not None
    assert task.direction == "pull"


def test_create_sync_log(db_session):
    """应能创建同步日志"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    task = SyncTask(
        connector_id=c.id, entity="order", direction="pull",
        cron_expression="0 * * * *", enabled=True,
    )
    db_session.add(task)
    db_session.flush()

    log = SyncLog(
        sync_task_id=task.id,
        connector_id=c.id,
        entity="order",
        direction="pull",
        status="success",
        total_records=100,
        success_count=98,
        failure_count=2,
        error_details={"failed_ids": ["001", "002"]},
    )
    db_session.add(log)
    db_session.flush()
    assert log.id is not None
    assert log.status == "success"
    assert log.failure_count == 2


def test_create_raw_data(db_session):
    """应能存储原始 JSONB 数据"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    raw = RawData(
        connector_id=c.id,
        entity="sales_order",
        external_id="SO-001",
        data={"FBillNo": "SO-001", "FAmount": 1000.00},
    )
    db_session.add(raw)
    db_session.flush()
    assert raw.id is not None
    assert raw.data["FBillNo"] == "SO-001"


def test_create_unified_customer(db_session):
    """应能创建统一客户记录"""
    customer = UnifiedCustomer(
        source_system="fenxiangxiaoke",
        external_id="C-001",
        name="测试公司",
        company="测试有限公司",
        phone="13800138000",
        email="test@example.com",
    )
    db_session.add(customer)
    db_session.flush()
    assert customer.id is not None
    assert customer.source_system == "fenxiangxiaoke"


def test_create_unified_order(db_session):
    """应能创建统一订单记录"""
    order = UnifiedOrder(
        source_system="kingdee_erp",
        external_id="SO-001",
        order_number="SO-001",
        order_type="sales",
        total_amount=1000.00,
        currency="CNY",
        status="approved",
    )
    db_session.add(order)
    db_session.flush()
    assert order.id is not None


def test_create_field_mapping(db_session):
    """应能创建字段映射记录"""
    mapping = FieldMapping(
        connector_type="kingdee_erp",
        source_entity="sales_order",
        target_table="unified_orders",
        source_field="FBillNo",
        target_field="order_number",
    )
    db_session.add(mapping)
    db_session.flush()
    assert mapping.id is not None


def test_unified_tables_have_source_traceability():
    """所有统一表应包含溯源字段"""
    for model in [UnifiedCustomer, UnifiedOrder, UnifiedProduct,
                  UnifiedInventory, UnifiedProject, UnifiedContact]:
        columns = {c.name for c in model.__table__.columns}
        assert "source_system" in columns, f"{model.__name__} missing source_system"
        assert "external_id" in columns, f"{model.__name__} missing external_id"
        assert "source_data_id" in columns, f"{model.__name__} missing source_data_id"
