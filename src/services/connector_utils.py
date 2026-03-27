import json
import logging

from sqlalchemy.orm import Session

from src.connectors.base import ConnectorError, connector_registry
from src.core.config import get_settings
from src.core.security import decrypt_value
from src.models.connector import Connector

logger = logging.getLogger(__name__)


def get_connector_instance(connector_type: str, db: Session):
    connector_model = (
        db.query(Connector).filter_by(connector_type=connector_type, enabled=True).first()
    )
    if not connector_model:
        raise ConnectorError(f"No enabled connector for type: {connector_type}")

    connector_class = connector_registry.get(connector_type)
    auth_config = connector_model.auth_config

    settings = get_settings()
    if isinstance(auth_config, dict) and "_encrypted" in auth_config:
        decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
        auth_config = json.loads(decrypted)

    config = {"base_url": connector_model.base_url}
    if isinstance(auth_config, dict):
        config.update(auth_config)

    connector = connector_class(config)
    connector.connect()
    return connector
