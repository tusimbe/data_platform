import json
import logging

from sqlalchemy.orm import Session

from src.services.connector_utils import get_connector_instance
from src.services.flow_service import StepResult

logger = logging.getLogger(__name__)


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

        # Use pre-built form_data from context if available (widget-level format),
        # otherwise fall back to generic wrapper.
        form_data = context.get("form_data") or [
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

    return {
        "FBillTypeID": {"FNumber": "XSTHD01_SYS"},
        "FDate": rr.get("return_date") or date.today().isoformat(),
        "FSaleOrgId": {"FNumber": rr.get("sale_org", "100")},
        "FStockOrgId": {"FNumber": rr.get("stock_org", "100")},
        "FRetcustId": {"FNumber": rr.get("customer_code", "")},
        "FReturnReason": {"FNumber": rr.get("return_reason", "7DWLY")},
        "FEntity": [
            {
                "FMaterialId": {"FNumber": rr.get("material_number", "")},
                "FUnitID": {"FNumber": rr.get("unit", "Pcs")},
                "FRealQty": rr.get("qty", 1),
                "FPrice": rr.get("price", 0),
                "FTaxPrice": rr.get("tax_price") or rr.get("price", 0),
                "FEntryTaxRate": rr.get("tax_rate", 13.0),
                "FStockId": {"FNumber": rr.get("warehouse", "SZCK006")},
                "FStockstatusId": {"FNumber": rr.get("stock_status", "KCZT01_SYS")},
                "FReturnType": {"FNumber": rr.get("return_type", "THLX01_SYS")},
            }
        ],
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
