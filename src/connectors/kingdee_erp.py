# src/connectors/kingdee_erp.py
import time
import logging
import re
from datetime import datetime

import httpx

from src.connectors.base import (
    BaseConnector,
    register_connector,
    ConnectorError,
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorPullError,
    ConnectorPushError,
)

logger = logging.getLogger(__name__)

KINGDEE_ENTITIES = {
    "sales_order": {
        "form_id": "SAL_SaleOrder",
        "description": "销售订单",
        "field_keys": [
            "FBillNo",
            "FDate",
            "FBillTypeID.FName",
            "FCustId.FName",
            "FSalerId.FName",
            "FSaleOrgId.FName",
            "FDocumentStatus",
            "FApproveDate",
            "FSaleDeptId.FName",
        ],
    },
    "purchase_order": {
        "form_id": "PUR_PurchaseOrder",
        "description": "采购订单",
        "field_keys": [
            "FBillNo",
            "FDate",
            "FBillTypeID.FName",
            "FSupplierId.FName",
            "FPurchaseOrgId.FName",
            "FDocumentStatus",
            "FApproveDate",
            "FPurchaseDeptId.FName",
        ],
    },
    "inventory": {
        "form_id": "STK_Inventory",
        "description": "库存",
        "field_keys": [
            "FID",
            "FStockId.FName",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FBaseQty",
            "FAuxQty",
            "FStockOrgId.FName",
            "FBaseUnitId.FName",
        ],
    },
    "material": {
        "form_id": "BD_MATERIAL",
        "description": "物料",
        "field_keys": [
            "FMaterialId",
            "FNumber",
            "FName",
            "FSpecification",
            "FDocumentStatus",
            "FBaseUnitId.FName",
            "FMaterialGroup.FName",
            "FForbidStatus",
        ],
    },
    "bom": {
        "form_id": "ENG_BOM",
        "description": "BOM",
        "field_keys": [
            "FID",
            "FBillNo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FDocumentStatus",
            "FUnitId.FName",
        ],
    },
    "voucher": {
        "form_id": "GL_VOUCHER",
        "description": "财务凭证",
        "field_keys": [
            "FBillNo",
            "FDate",
            "FAccountBookID.FName",
            "FDocumentStatus",
            "FVOUCHERGROUPNO",
        ],
    },
}

MAX_PAGES = 500
_SAFE_FILTER_VALUE = re.compile(r"^[\w\s\-\.:/]+$")

_AUTH_PATH = "Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
_QUERY_PATH = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
_SAVE_PATH = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc"


@register_connector("kingdee_erp")
class KingdeeERPConnector(BaseConnector):
    def __init__(self, config: dict):
        super().__init__(config)
        self._authenticated = False
        self._client = httpx.Client(timeout=30.0)

    def _api_url(self, path: str) -> str:
        return f"{self.config['base_url']}/k3cloud/{path}"

    def connect(self) -> None:
        payload = {
            "acctID": self.config["acct_id"],
            "username": self.config.get("username", ""),
            "password": self.config.get("password", ""),
            "lcid": self.config.get("lcid", 2052),
        }
        result = self._request("POST", self._api_url(_AUTH_PATH), json=payload)

        if not isinstance(result, dict):
            raise ConnectorError(f"Unexpected auth response: {type(result)}")

        if not result.get("IsSuccessByAPI") and result.get("LoginResultType") != 1:
            raise ConnectorError(f"Auth failed: {result.get('Message') or result}")

        self._authenticated = True
        logger.info("Kingdee ERP auth succeeded")

    def disconnect(self) -> None:
        self._authenticated = False
        self._client.close()

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            self._request("GET", self._api_url(""))
            latency = (time.time() - start) * 1000
            return HealthStatus(status="healthy", latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthStatus(status="unhealthy", latency_ms=round(latency, 2), error=str(e))

    def list_entities(self) -> list[EntityInfo]:
        return [
            EntityInfo(name=name, description=meta["description"])
            for name, meta in KINGDEE_ENTITIES.items()
        ]

    @staticmethod
    def _sanitize_filter_value(value: str) -> str:
        str_val = str(value)
        if not _SAFE_FILTER_VALUE.match(str_val):
            raise ConnectorPullError("Invalid filter value: contains unsafe characters")
        return str_val

    @staticmethod
    def _rows_to_dicts(rows: list[list], field_keys: list[str]) -> list[dict]:
        return [dict(zip(field_keys, row)) for row in rows if isinstance(row, list)]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in KINGDEE_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        meta = KINGDEE_ENTITIES[entity]
        form_id = meta["form_id"]
        field_keys = meta["field_keys"]
        url = self._api_url(_QUERY_PATH)

        filter_string = ""
        if since:
            filter_string = f"FModifyDate >= '{since.strftime('%Y-%m-%d %H:%M:%S')}'"
        if filters:
            extra = " AND ".join(
                f"{self._sanitize_filter_value(k)} = '{self._sanitize_filter_value(v)}'"
                for k, v in filters.items()
            )
            filter_string = f"{filter_string} AND {extra}" if filter_string else extra

        try:
            all_records: list[dict] = []
            start_row = 0
            page_limit = 2000
            page_count = 0

            while True:
                page_count += 1
                if page_count > MAX_PAGES:
                    logger.warning(f"Reached max page limit ({MAX_PAGES}) for entity={entity}")
                    break

                payload = {
                    "data": {
                        "FormId": form_id,
                        "FieldKeys": ",".join(field_keys),
                        "FilterString": filter_string,
                        "OrderString": "",
                        "TopRowCount": 0,
                        "StartRow": start_row,
                        "Limit": page_limit,
                    }
                }

                result = self._request("POST", url, json=payload)
                raw_rows = result if isinstance(result, list) else []
                batch = self._rows_to_dicts(raw_rows, field_keys)
                all_records.extend(batch)

                if len(raw_rows) < page_limit:
                    break

                start_row += page_limit

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"金蝶ERP拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        if entity not in KINGDEE_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        form_id = KINGDEE_ENTITIES[entity]["form_id"]
        url = self._api_url(_SAVE_PATH)

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                payload = {"data": {"FormId": form_id, "Model": record}}
                self._request("POST", url, json=payload)
                success_count += 1
            except Exception as e:
                failure_count += 1
                logger.warning(
                    f"Failed to push {entity} record {record.get('FBillNo', 'unknown')}: {e}"
                )
                failures.append(
                    {
                        "record": record.get("FBillNo", "unknown"),
                        "error": str(e),
                    }
                )

        if failure_count > 0:
            logger.warning(f"Push {entity}: {failure_count}/{len(records)} records failed")

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        return KINGDEE_ENTITIES.get(entity, {})

    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        pass
