import json
import logging

from sqlalchemy.orm import Session

from src.services.connector_utils import get_connector_instance
from src.services.flow_service import StepResult

logger = logging.getLogger(__name__)


def create_feishu_approval_handler(context: dict, db: Session) -> StepResult:
    logger.info("Executing create_feishu_approval_handler")
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        approval_code = connector.config.get("approval_code", "")
        open_id = context.get("applicant_open_id") or connector.config.get("open_user_id", "")
        return_request = context.get("return_request", {})
        logger.info(
            "create_feishu_approval_handler: applicant_open_id=%s has_return_request=%s",
            bool(open_id),
            bool(return_request),
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
        logger.exception("create_feishu_approval_handler failed: %s", e)
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("create_feishu_approval_handler: failed to disconnect connector")


def poll_feishu_approval_handler(context: dict, db: Session) -> StepResult:
    instance_code = context.get("approval_instance_code", "")
    logger.info("Executing poll_feishu_approval_handler: approval_instance_code=%s", instance_code)
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        result = connector.get_approval_instance(instance_code)
        status = result.get("status", "PENDING")
        logger.info("poll_feishu_approval_handler: status=%s", status)

        if status == "APPROVED":
            return StepResult(
                status="completed",
                data={"approval_status": "APPROVED", "approval_data": result},
            )
        if status in ("REJECTED", "CANCELED"):
            return StepResult(status="cancelled", error=f"Approval {status}")
        return StepResult(status="waiting")
    except Exception as e:
        logger.exception("poll_feishu_approval_handler failed: %s", e)
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("poll_feishu_approval_handler: failed to disconnect connector")


def create_erp_return_order_handler(context: dict, db: Session) -> StepResult:
    return_request = context.get("return_request", {})
    logger.info(
        "Executing create_erp_return_order_handler: customer_code=%s approval_status=%s",
        return_request.get("customer_code", ""),
        context.get("approval_status", ""),
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("return_order_bill_id")
        existing_bill_no = context.get("return_order_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_return_order_handler: bill_id=%s already exists, skipping Save",
                existing_bill_id,
            )
            try:
                connector.submit("SAL_RETURNSTOCK", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Submit (resume) failed: %s, attempting audit", e)
            try:
                connector.audit("SAL_RETURNSTOCK", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Audit (resume) failed: %s", e)
            return StepResult(
                status="completed",
                data={
                    "return_order_bill_no": existing_bill_no,
                    "return_order_bill_id": existing_bill_id,
                },
            )

        model = {
            "FBillTypeID": {"FNumber": "XSTHD01_SYS"},
            "FReturnDate": return_request.get("return_date", ""),
            "FCustId": {"FNumber": return_request.get("customer_code", "")},
            "FNote": "中台自动创建-退货流程",
        }
        result = connector.save_then_submit_audit("SAL_RETURNSTOCK", model)
        return StepResult(
            status="completed",
            data={
                "return_order_bill_no": result["bill_no"],
                "return_order_bill_id": result["bill_id"],
            },
        )
    except Exception as e:
        logger.exception("create_erp_return_order_handler failed: %s", e)
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("create_erp_return_order_handler: failed to disconnect connector")


def create_erp_negative_receivable_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing create_erp_negative_receivable_handler: return_order_bill_no=%s",
        context.get("return_order_bill_no", ""),
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("receivable_bill_id")
        existing_bill_no = context.get("receivable_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_negative_receivable_handler: bill_id=%s already exists, skipping Save",
                existing_bill_id,
            )
            try:
                connector.submit("AR_RECEIVABLE", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Submit (resume) failed: %s, attempting audit", e)
            try:
                connector.audit("AR_RECEIVABLE", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Audit (resume) failed: %s", e)
            return StepResult(
                status="completed",
                data={
                    "receivable_bill_no": existing_bill_no,
                    "receivable_bill_id": existing_bill_id,
                },
            )

        model = {
            "FBillTypeID": {"FNumber": "YSD01_SYS"},
            "FCustId": {"FNumber": context.get("return_request", {}).get("customer_code", "")},
            "FNote": f"中台自动创建-关联退货单 {context.get('return_order_bill_no', '')}",
        }
        result = connector.save_then_submit_audit("AR_RECEIVABLE", model)
        return StepResult(
            status="completed",
            data={
                "receivable_bill_no": result["bill_no"],
                "receivable_bill_id": result["bill_id"],
            },
        )
    except Exception as e:
        logger.exception("create_erp_negative_receivable_handler failed: %s", e)
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning(
                    "create_erp_negative_receivable_handler: failed to disconnect connector"
                )


def create_erp_refund_bill_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing create_erp_refund_bill_handler: receivable_bill_no=%s",
        context.get("receivable_bill_no", ""),
    )
    connector = None
    try:
        connector = get_connector_instance("kingdee_erp", db)
        existing_bill_id = context.get("refund_bill_id")
        existing_bill_no = context.get("refund_bill_no")
        if existing_bill_id:
            logger.info(
                "Resuming create_erp_refund_bill_handler: bill_id=%s already exists, skipping Save",
                existing_bill_id,
            )
            try:
                connector.submit("AR_REFUNDBILL", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Submit (resume) failed: %s, attempting audit", e)
            try:
                connector.audit("AR_REFUNDBILL", existing_bill_id, existing_bill_no)
            except Exception as e:
                logger.warning("Audit (resume) failed: %s", e)
            return StepResult(
                status="completed",
                data={"refund_bill_no": existing_bill_no, "refund_bill_id": existing_bill_id},
            )

        model = {
            "FBillTypeID": {"FNumber": "SKTKD01_SYS"},
            "FCustId": {"FNumber": context.get("return_request", {}).get("customer_code", "")},
            "FNote": f"中台自动创建-关联应收单 {context.get('receivable_bill_no', '')}",
        }
        result = connector.save_then_submit_audit("AR_REFUNDBILL", model)
        return StepResult(
            status="completed",
            data={
                "refund_bill_no": result["bill_no"],
                "refund_bill_id": result["bill_id"],
            },
        )
    except Exception as e:
        logger.exception("create_erp_refund_bill_handler failed: %s", e)
        return StepResult(status="failed", error=str(e))
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("create_erp_refund_bill_handler: failed to disconnect connector")


def notify_finance_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing notify_finance_handler: return_order=%s receivable=%s refund=%s",
        context.get("return_order_bill_no", "N/A"),
        context.get("receivable_bill_no", "N/A"),
        context.get("refund_bill_no", "N/A"),
    )
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        receive_id = context.get("finance_notify_id") or connector.config.get(
            "finance_notify_id", ""
        )
        if not receive_id:
            logger.warning("notify_finance_handler: no finance_notify_id found, skip sending")
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
            logger.warning("notify_finance_handler send failed: %s", e)
            return StepResult(
                status="completed",
                data={"finance_notified": False, "notify_error": str(e)},
            )
    except Exception as e:
        logger.exception("notify_finance_handler failed before send: %s", e)
        return StepResult(
            status="completed",
            data={"finance_notified": False, "notify_error": str(e)},
        )
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("notify_finance_handler: failed to disconnect connector")


def notify_sales_handler(context: dict, db: Session) -> StepResult:
    logger.info(
        "Executing notify_sales_handler: applicant_open_id=%s return_order=%s refund=%s",
        bool(context.get("applicant_open_id")),
        context.get("return_order_bill_no", "N/A"),
        context.get("refund_bill_no", "N/A"),
    )
    connector = None
    try:
        connector = get_connector_instance("feishu", db)
        receive_id = context.get("sales_notify_id") or context.get("applicant_open_id", "")
        if not receive_id:
            logger.warning("notify_sales_handler: no sales recipient found, skip sending")
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
            logger.warning("notify_sales_handler send failed: %s", e)
            return StepResult(
                status="completed",
                data={"sales_notified": False, "notify_error": str(e)},
            )
    except Exception as e:
        logger.exception("notify_sales_handler failed before send: %s", e)
        return StepResult(
            status="completed",
            data={"sales_notified": False, "notify_error": str(e)},
        )
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("notify_sales_handler: failed to disconnect connector")


STEP_HANDLERS = {
    "create_feishu_approval": create_feishu_approval_handler,
    "poll_feishu_approval": poll_feishu_approval_handler,
    "create_erp_return_order": create_erp_return_order_handler,
    "create_erp_negative_receivable": create_erp_negative_receivable_handler,
    "create_erp_refund_bill": create_erp_refund_bill_handler,
    "notify_finance": notify_finance_handler,
    "notify_sales": notify_sales_handler,
}
