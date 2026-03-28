import json
import logging

from sqlalchemy.orm import Session

from src.services.connector_utils import get_connector_instance
from src.services.flow_service import StepResult

logger = logging.getLogger(__name__)

# --- CRM field name → ERP / Feishu mapping tables ---

_CRM_WAREHOUSE_TO_ERP = {
    "option1": "KMCK007",  # 深圳潜行退货仓（昆明）
    "Uzq85kDP1": "SZCK006",  # 赣州潜行退货仓（赣州）→ mapped to 深圳潜行退货仓(GZ)
}

_CRM_RETURN_TYPE_TO_ERP = {
    "option1": "7DWLY",  # 7天无理由退货
    "5c9krzyPJ": "THLX01_SYS",  # 质量问题退换货 → 退货
}

_CRM_PRODUCT_LINE_TO_FEISHU = {
    "水下机器人": "option_1BRHZ0X0S2OE8",
    "智慧渔业": "option_1BRHZ0X0S2OE8",
    "清洁机器人": "option_11SSIMCHSF18G",
}

_CRM_COMPANY_TO_FEISHU = {
    "深圳潜行创新科技有限公司": "ly5f0c8e-2zxry5kv6mo-0",
}

_CRM_WAREHOUSE_TO_FEISHU = {
    "option1": "lugeg8ud-bhryml0yll-1",  # 昆明仓
    "Uzq85kDP1": "option_0",  # 赣州仓
}

_CRM_RETURN_TYPE_TO_FEISHU = {
    "option1": "option_1Y3XM46ER8RK0",  # 7天无理由退货
    "5c9krzyPJ": "option_1W8HOSU7YBY80",  # 质量问题 → 退货选项
}


def _map_crm_return_to_context(crm_record: dict) -> dict:
    """Translate a raw CRM return_order record into the flow context return_request dict."""
    details = crm_record.get("details", [])
    warehouse_code = crm_record.get("return_warehouse__c", "option1")

    items = []
    total_amount = 0.0
    for detail in details:
        material_number = detail.get("field_0j4GR__c", "")
        qty = int(detail.get("field_HgHiC__c", "1") or "1")
        unit_price = float(detail.get("field_6xGlQ__c", "0") or "0")
        amount = float(detail.get("field_Q5wwd__c", "0") or "0")
        total_amount += amount
        items.append(
            {
                "material_number": material_number,
                "product_name": detail.get("field_BS878__c__r", ""),
                "qty": qty,
                "price": unit_price,
                "tax_price": unit_price,
            }
        )

    if not items:
        amt_str = crm_record.get("field_P1jbp__c", "0")
        total_amount = float(amt_str) if amt_str else 0.0

    return {
        "crm_record_id": crm_record.get("_id", ""),
        "crm_return_name": crm_record.get("name", ""),
        "customer_name": crm_record.get("field_mlRW0__c__r", ""),
        "customer_code": "DS0002",
        "erp_order_no": crm_record.get("erp_sale_order_id__c", ""),
        "product_line": crm_record.get("product_line__c", ""),
        "company": crm_record.get("single_line_text__c", ""),
        "return_type_code": crm_record.get("field_8r1i7__c", ""),
        "return_type_name": crm_record.get("field_8r1i7__c__r", ""),
        "warehouse": _CRM_WAREHOUSE_TO_ERP.get(warehouse_code, "SZCK006"),
        "warehouse_code": warehouse_code,
        "return_reason": _CRM_RETURN_TYPE_TO_ERP.get(crm_record.get("field_8r1i7__c", ""), "7DWLY"),
        "price": total_amount,
        "refund_amount": total_amount,
        "items": items,
    }


def _map_crm_return_to_feishu_form(return_request: dict) -> list[dict]:
    """Build 飞书审批 form_data widgets from a mapped return_request dict."""
    items = return_request.get("items", [])
    product_names = ", ".join(it.get("product_name", "") for it in items) or "N/A"
    material_numbers = ", ".join(it.get("material_number", "") for it in items) or "N/A"
    total_qty = sum(it.get("qty", 0) for it in items) or 1
    total_amount = return_request.get("price", 0)

    product_line = return_request.get("product_line", "")
    product_line_option = _CRM_PRODUCT_LINE_TO_FEISHU.get(product_line, "option_1BRHZ0X0S2OE8")

    company = return_request.get("company", "")
    company_option = _CRM_COMPANY_TO_FEISHU.get(company, "ly5f0c8e-2zxry5kv6mo-0")

    warehouse_code = return_request.get("warehouse_code", "option1")
    warehouse_option = _CRM_WAREHOUSE_TO_FEISHU.get(warehouse_code, "lugeg8ud-bhryml0yll-1")

    return_type_code = return_request.get("return_type_code", "option1")
    return_option = _CRM_RETURN_TYPE_TO_FEISHU.get(return_type_code, "option_1W8HOSU7YBY80")

    return_type_option = "option_1Y3XM46ER8RK0"
    if return_type_code == "option1":
        return_type_option = "option_1Y3XM46ER8RK0"

    return [
        {
            "id": "widget17097041122290001",
            "type": "input",
            "value": f"退货申请-{return_request.get('crm_return_name', '')}",
        },
        {"id": "widget17199855863190001", "type": "radioV2", "value": company_option},
        {
            "id": "widget17044374922644145592676844312",
            "type": "input",
            "value": return_request.get("erp_order_no", ""),
        },
        {
            "id": "widget17044374925130758661767103793",
            "type": "radioV2",
            "value": product_line_option,
        },
        {"id": "widget17044374923208668401250281164", "type": "radioV2", "value": return_option},
        {"id": "widget17044374924784750207991989514", "type": "radioV2", "value": warehouse_option},
        {"id": "widget1704437492417154337041962472", "type": "radioV2", "value": "option_1"},
        {
            "id": "widget17103188979720001",
            "type": "radioV2",
            "value": "ltpjpnp2-zsmkrpel5ms-0" if len(items) <= 1 else "ltpjpnp2-776lugahwm4-0",
        },
        {
            "id": "widget17044374922647633089730529883",
            "type": "radioV2",
            "value": return_type_option,
        },
        {"id": "widget17103190108380001", "type": "input", "value": product_names[:200]},
        {"id": "widget17119605722650001", "type": "input", "value": material_numbers[:200]},
        {"id": "widget17103190357250001", "type": "input", "value": str(total_qty)},
        {"id": "widget17103190520600001", "type": "amount", "value": str(total_amount)},
        {"id": "widget17044374921415902955164242986", "type": "input", "value": "待填写"},
        {
            "id": "widget17044374924939488823226624671",
            "type": "textarea",
            "value": f"中台自动发起-{return_request.get('return_type_name', '')}",
        },
        {"id": "widget17044374922689175280575462519", "type": "radioV2", "value": "option_1"},
        {"id": "widget1704437492636905943464584325", "type": "input", "value": "待制单"},
        {"id": "widget1704437492541973339237646441", "type": "input", "value": "待审核"},
        {
            "id": "widget17044374927776950585882470463",
            "type": "textarea",
            "value": "中台自动发起-待评估",
        },
        {
            "id": "widget17044374924681069888512789",
            "type": "textarea",
            "value": "中台自动发起-待确认",
        },
        {
            "id": "widget17044374925851700580832692851",
            "type": "textarea",
            "value": "中台自动发起-待稽核",
        },
    ]


def create_feishu_approval_handler(context: dict, db: Session) -> StepResult:
    logger.info("Executing create_feishu_approval_handler", extra={})
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        approval_code = connector.config.get("approval_code", "")
        open_id = context.get("applicant_open_id") or connector.config.get("open_user_id", "")
        return_request = context.get("return_request", {})
        logger.info(
            "create_feishu_approval_handler context resolved",
            extra={
                "has_applicant_open_id": bool(open_id),
                "has_return_request": bool(return_request),
            },
        )

        form_data = context.get("form_data")
        if not form_data and return_request:
            form_data = _map_crm_return_to_feishu_form(return_request)
        if not form_data:
            form_data = [
                {
                    "id": "widget17097041122290001",
                    "type": "input",
                    "value": json.dumps(return_request, ensure_ascii=False),
                }
            ]

        instance_code = connector.create_approval_instance(approval_code, open_id, form_data)
        return StepResult(status="completed", data={"approval_instance_code": instance_code})
    except Exception as e:
        logger.exception(
            "create_feishu_approval_handler failed",
            extra={"error": str(e)},
        )
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "create_feishu_approval_handler failed to disconnect connector",
                    extra={"connector_name": "feishu"},
                )


def poll_feishu_approval_handler(context: dict, db: Session) -> StepResult:
    instance_code = context.get("approval_instance_code", "")
    logger.info(
        "Executing poll_feishu_approval_handler",
        extra={"approval_instance_code": instance_code},
    )
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        result = connector.get_approval_instance(instance_code)
        status = result.get("status", "PENDING")
        logger.info(
            "poll_feishu_approval_handler status received",
            extra={"approval_status": status, "approval_instance_code": instance_code},
        )

        if status == "APPROVED":
            return StepResult(
                status="completed",
                data={"approval_status": "APPROVED", "approval_data": result},
            )
        if status in ("REJECTED", "CANCELED"):
            return StepResult(status="cancelled", error=f"Approval {status}")
        return StepResult(status="waiting")
    except Exception as e:
        logger.exception(
            "poll_feishu_approval_handler failed",
            extra={"approval_instance_code": instance_code, "error": str(e)},
        )
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "poll_feishu_approval_handler failed to disconnect connector",
                    extra={"connector_name": "feishu"},
                )


def _build_return_order_model(rr: dict) -> dict:
    from datetime import date

    items = rr.get("items", [])
    warehouse = rr.get("warehouse", "SZCK006")

    if items:
        entity_lines = []
        for item in items:
            entity_lines.append(
                {
                    "FMaterialId": {"FNumber": item.get("material_number", "")},
                    "FUnitID": {"FNumber": item.get("unit", "Pcs")},
                    "FRealQty": item.get("qty", 1),
                    "FPrice": item.get("price", 0),
                    "FTaxPrice": item.get("tax_price") or item.get("price", 0),
                    "FEntryTaxRate": item.get("tax_rate", 13.0),
                    "FStockId": {"FNumber": warehouse},
                    "FStockstatusId": {"FNumber": item.get("stock_status", "KCZT01_SYS")},
                    "FReturnType": {"FNumber": rr.get("return_type", "THLX01_SYS")},
                }
            )
    else:
        entity_lines = [
            {
                "FMaterialId": {"FNumber": rr.get("material_number", "")},
                "FUnitID": {"FNumber": rr.get("unit", "Pcs")},
                "FRealQty": rr.get("qty", 1),
                "FPrice": rr.get("price", 0),
                "FTaxPrice": rr.get("tax_price") or rr.get("price", 0),
                "FEntryTaxRate": rr.get("tax_rate", 13.0),
                "FStockId": {"FNumber": warehouse},
                "FStockstatusId": {"FNumber": rr.get("stock_status", "KCZT01_SYS")},
                "FReturnType": {"FNumber": rr.get("return_type", "THLX01_SYS")},
            }
        ]

    return {
        "FBillTypeID": {"FNumber": "XSTHD01_SYS"},
        "FDate": rr.get("return_date") or date.today().isoformat(),
        "FSaleOrgId": {"FNumber": rr.get("sale_org", "100")},
        "FStockOrgId": {"FNumber": rr.get("stock_org", "100")},
        "FRetcustId": {"FNumber": rr.get("customer_code", "")},
        "FReturnReason": {"FNumber": rr.get("return_reason", "7DWLY")},
        "FEntity": entity_lines,
    }


def create_erp_return_order_handler(context: dict, db: Session) -> StepResult:
    return_request = context.get("return_request", {})
    logger.info(
        "Executing create_erp_return_order_handler",
        extra={
            "customer_code": return_request.get("customer_code", ""),
            "approval_status": context.get("approval_status", ""),
        },
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("return_order_bill_id")
        existing_bill_no = context.get("return_order_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_return_order_handler with existing bill",
                extra={
                    "existing_bill_id": existing_bill_id,
                    "existing_bill_no": existing_bill_no,
                },
            )
            try:
                connector.submit("SAL_RETURNSTOCK", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP return order submit on resume failed; attempting audit",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            try:
                connector.audit("SAL_RETURNSTOCK", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP return order audit on resume failed",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            return StepResult(
                status="completed",
                data={
                    "return_order_bill_no": existing_bill_no,
                    "return_order_bill_id": existing_bill_id,
                },
            )

        model = _build_return_order_model(return_request)
        result = connector.save_then_submit_audit("SAL_RETURNSTOCK", model)
        return StepResult(
            status="completed",
            data={
                "return_order_bill_no": result["bill_no"],
                "return_order_bill_id": result["bill_id"],
            },
        )
    except Exception as e:
        logger.exception(
            "create_erp_return_order_handler failed",
            extra={"error": str(e)},
        )
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "create_erp_return_order_handler failed to disconnect connector",
                    extra={"connector_name": "kingdee_erp"},
                )


def create_erp_negative_receivable_handler(context: dict, db: Session) -> StepResult:
    return_order_bill_no = context.get("return_order_bill_no", "")
    logger.info(
        "Executing create_erp_negative_receivable_handler",
        extra={"return_order_bill_no": return_order_bill_no},
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("receivable_bill_id")
        existing_bill_no = context.get("receivable_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_negative_receivable_handler with existing bill",
                extra={
                    "existing_bill_id": existing_bill_id,
                    "existing_bill_no": existing_bill_no,
                },
            )
            try:
                connector.submit("AR_RECEIVABLE", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP negative receivable submit on resume failed; attempting audit",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            try:
                connector.audit("AR_RECEIVABLE", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP negative receivable audit on resume failed",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            return StepResult(
                status="completed",
                data={
                    "receivable_bill_no": existing_bill_no,
                    "receivable_bill_id": existing_bill_id,
                },
            )

        if not return_order_bill_no:
            return StepResult(status="failed", error="Missing return_order_bill_no in context")

        bills = connector.query_bills(
            form_id="AR_RECEIVABLE",
            field_keys=["FID", "FBillNo", "FDocumentStatus", "FALLAMOUNTFOR"],
            filter_string=f"FSOURCEBILLNO = '{return_order_bill_no}'",
        )
        if not bills:
            return StepResult(
                status="failed",
                error=f"No auto-generated receivable found for return order {return_order_bill_no}",
            )

        bill = bills[0]
        bill_id = str(bill["FID"])
        bill_no = str(bill["FBillNo"])
        doc_status = bill.get("FDocumentStatus", "")
        logger.info(
            "Found auto-generated receivable",
            extra={
                "receivable_bill_no": bill_no,
                "receivable_bill_id": bill_id,
                "document_status": doc_status,
            },
        )

        if doc_status == "C":
            logger.info(
                "Receivable already audited; skipping submit and audit",
                extra={"receivable_bill_no": bill_no, "receivable_bill_id": bill_id},
            )
        else:
            if doc_status not in ("B", "C"):
                try:
                    connector.submit("AR_RECEIVABLE", bill_id, bill_no)
                except Exception as e:
                    logger.warning(
                        "Submit receivable failed; attempting audit anyway",
                        extra={
                            "receivable_bill_no": bill_no,
                            "receivable_bill_id": bill_id,
                            "error": str(e),
                        },
                    )
            connector.audit("AR_RECEIVABLE", bill_id, bill_no)

        return StepResult(
            status="completed",
            data={
                "receivable_bill_no": bill_no,
                "receivable_bill_id": bill_id,
                "receivable_amount": bill.get("FALLAMOUNTFOR"),
            },
        )
    except Exception as e:
        logger.exception(
            "create_erp_negative_receivable_handler failed",
            extra={"return_order_bill_no": return_order_bill_no, "error": str(e)},
        )
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "create_erp_negative_receivable_handler failed to disconnect connector",
                    extra={"connector_name": "kingdee_erp"},
                )


def _build_refund_bill_model(context: dict) -> dict:
    from datetime import date

    rr = context.get("return_request", {})
    amount = rr.get("refund_amount") or rr.get("price", 0)
    return {
        "FBillTypeID": {"FNumber": "SKTKDLX01_SYS"},
        "FDate": date.today().isoformat(),
        "FPAYORGID": {"FNumber": rr.get("sale_org", "100")},
        "FCONTACTUNIT": {"FNumber": rr.get("customer_code", "")},
        "FSETTLECUR": {"FNumber": "PRE001"},
        "FPURPOSEID": {"FNumber": "SFKYT01_SYS"},
        "FREFUNDBILLENTRY": [
            {
                "FSETTLETYPEID": {"FNumber": rr.get("settle_type", "JSFS04_SYS")},
                "FREFUNDAMOUNTFOR_E": amount,
                "FREALREFUNDAMOUNTFOR": amount,
                "FNOTE": f"中台退款-退货单{context.get('return_order_bill_no', '')}",
                "FPURPOSEID": {"FNumber": "SFKYT01_SYS"},
                "FACCOUNTID": {"FNumber": rr.get("bank_account", "755930370110902")},
            }
        ],
    }


def create_erp_refund_bill_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing create_erp_refund_bill_handler",
        extra={"receivable_bill_no": context.get("receivable_bill_no", "")},
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("refund_bill_id")
        existing_bill_no = context.get("refund_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_refund_bill_handler with existing bill",
                extra={
                    "existing_bill_id": existing_bill_id,
                    "existing_bill_no": existing_bill_no,
                },
            )
            try:
                connector.submit("AR_REFUNDBILL", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP refund bill submit on resume failed; attempting audit",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            try:
                connector.audit("AR_REFUNDBILL", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning(
                    "ERP refund bill audit on resume failed",
                    extra={"existing_bill_id": existing_bill_id, "error": str(e)},
                )
            return StepResult(
                status="completed",
                data={"refund_bill_no": existing_bill_no, "refund_bill_id": existing_bill_id},
            )

        model = _build_refund_bill_model(context)
        result = connector.save_then_submit_audit("AR_REFUNDBILL", model)
        return StepResult(
            status="completed",
            data={
                "refund_bill_no": result["bill_no"],
                "refund_bill_id": result["bill_id"],
            },
        )
    except Exception as e:
        logger.exception(
            "create_erp_refund_bill_handler failed",
            extra={"error": str(e)},
        )
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "create_erp_refund_bill_handler failed to disconnect connector",
                    extra={"connector_name": "kingdee_erp"},
                )


def notify_finance_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing notify_finance_handler",
        extra={
            "return_order_bill_no": context.get("return_order_bill_no", "N/A"),
            "receivable_bill_no": context.get("receivable_bill_no", "N/A"),
            "refund_bill_no": context.get("refund_bill_no", "N/A"),
        },
    )
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        receive_id = context.get("finance_notify_id") or connector.config.get(
            "finance_notify_id", ""
        )
        if not receive_id:
            logger.warning(
                "notify_finance_handler no finance recipient found; skip sending",
                extra={},
            )
            return StepResult(status="completed", data={"finance_notified": False})

        text = (
            f"【退货流程通知-财务】\n"
            f"退货单号: {context.get('return_order_bill_no', 'N/A')}\n"
            f"应收单号: {context.get('receivable_bill_no', 'N/A')}\n"
            f"退款单号: {context.get('refund_bill_no', 'N/A')}\n"
            f"请及时进行银行审核。"
        )

        try:
            connector.send_message(receive_id, "text", {"text": text})
            return StepResult(status="completed", data={"finance_notified": True})
        except Exception as e:
            logger.warning(
                "notify_finance_handler send failed",
                extra={"receive_id": receive_id, "error": str(e)},
            )
            return StepResult(
                status="completed",
                data={"finance_notified": False, "notify_error": str(e)},
            )
    except Exception as e:
        logger.exception(
            "notify_finance_handler failed before send",
            extra={"error": str(e)},
        )
        return StepResult(
            status="completed",
            data={"finance_notified": False, "notify_error": str(e)},
        )
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "notify_finance_handler failed to disconnect connector",
                    extra={"connector_name": "feishu"},
                )


def notify_sales_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing notify_sales_handler",
        extra={
            "has_applicant_open_id": bool(context.get("applicant_open_id")),
            "return_order_bill_no": context.get("return_order_bill_no", "N/A"),
            "refund_bill_no": context.get("refund_bill_no", "N/A"),
        },
    )
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        receive_id = context.get("sales_notify_id") or context.get("applicant_open_id", "")
        if not receive_id:
            logger.warning(
                "notify_sales_handler no sales recipient found; skip sending",
                extra={},
            )
            return StepResult(status="completed", data={"sales_notified": False})

        text = (
            f"【退货流程通知-销售】\n"
            f"退货流程已完成。\n"
            f"退货单号: {context.get('return_order_bill_no', 'N/A')}\n"
            f"退款单号: {context.get('refund_bill_no', 'N/A')}\n"
            f"财务已收到通知，请关注后续进度。"
        )

        try:
            connector.send_message(receive_id, "text", {"text": text})
            return StepResult(status="completed", data={"sales_notified": True})
        except Exception as e:
            logger.warning(
                "notify_sales_handler send failed",
                extra={"receive_id": receive_id, "error": str(e)},
            )
            return StepResult(
                status="completed",
                data={"sales_notified": False, "notify_error": str(e)},
            )
    except Exception as e:
        logger.exception(
            "notify_sales_handler failed before send",
            extra={"error": str(e)},
        )
        return StepResult(
            status="completed",
            data={"sales_notified": False, "notify_error": str(e)},
        )
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "notify_sales_handler failed to disconnect connector",
                    extra={"connector_name": "feishu"},
                )


STEP_HANDLERS = {
    "create_feishu_approval": create_feishu_approval_handler,
    "poll_feishu_approval": poll_feishu_approval_handler,
    "create_erp_return_order": create_erp_return_order_handler,
    "create_erp_negative_receivable": create_erp_negative_receivable_handler,
    "create_erp_refund_bill": create_erp_refund_bill_handler,
    "notify_finance": notify_finance_handler,
    "notify_sales": notify_sales_handler,
}
