from src.connectors.base import (  # noqa: F401
    BaseConnector,
    ConnectorRegistry,
    connector_registry,
    register_connector,
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorPullError,
    ConnectorPushError,
)

# 导入所有连接器以触发注册
from src.connectors.kingdee_erp import KingdeeERPConnector  # noqa: F401
from src.connectors.kingdee_plm import KingdeePLMConnector  # noqa: F401
from src.connectors.feishu import FeishuConnector  # noqa: F401
from src.connectors.fenxiangxiaoke import FenxiangxiaokeConnector  # noqa: F401
from src.connectors.lingxing import LingxingConnector  # noqa: F401
from src.connectors.zentao import ZentaoConnector  # noqa: F401
