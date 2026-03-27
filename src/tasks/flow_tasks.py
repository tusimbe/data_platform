import logging
from datetime import datetime, timedelta, timezone

from src.core.celery_app import celery_app
from src.core.database import get_session_local
from src.models.flow import FlowDefinition, FlowInstance
from src.services.connector_utils import get_connector_instance
from src.services.flow_service import advance_flow, check_step_timeout, create_instance

logger = logging.getLogger(__name__)


def _extract_return_entity(flow_def: FlowDefinition) -> str:
    steps = flow_def.steps if isinstance(flow_def.steps, list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("return_entity"):
            return step["return_entity"]
        step_config = step.get("config")
        if isinstance(step_config, dict) and step_config.get("return_entity"):
            return step_config["return_entity"]
    return "return_order"


def _extract_record_id(record: dict) -> str:
    return str(record.get("_id") or record.get("objectId") or record.get("dataObjectId") or "")


@celery_app.task(name="flow.advance_flow", max_retries=3, acks_late=True)
def advance_flow_task(instance_id: int, chain_depth: int = 0):
    """Execute the next step of a flow instance. Self-chains for instant steps."""
    MAX_CHAIN_DEPTH = 20
    if chain_depth > MAX_CHAIN_DEPTH:
        logger.error(
            f"advance_flow_task: chain_depth {chain_depth} exceeds max {MAX_CHAIN_DEPTH} for instance {instance_id}"
        )
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            instance = session.query(FlowInstance).filter_by(id=instance_id).first()
            if instance and instance.status == "running":
                instance.status = "failed"
                instance.error_message = f"Chain depth limit exceeded ({MAX_CHAIN_DEPTH})"
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
        return {"status": "failed", "error": f"Chain depth limit exceeded ({MAX_CHAIN_DEPTH})"}

    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        result = advance_flow(instance_id, session)
        session.commit()

        # Self-chain: if status is "running", immediately execute next step
        if result.get("status") == "running":
            advance_flow_task.delay(instance_id, chain_depth=chain_depth + 1)

        return result
    except Exception as e:
        session.rollback()
        logger.exception(f"advance_flow_task failed for instance {instance_id}: {e}")
        try:
            instance = session.query(FlowInstance).filter_by(id=instance_id).first()
            if instance and instance.status == "running":
                instance.status = "failed"
                instance.error_message = f"Task error: {str(e)[:500]}"
                session.commit()
        except Exception:
            session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


@celery_app.task(name="flow.poll_waiting_flows")
def poll_waiting_flows():
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        waiting_instances = (
            session.query(FlowInstance).filter(FlowInstance.status == "waiting").limit(50).all()
        )

        if not waiting_instances:
            return {"status": "ok", "checked": 0}

        results = []
        dispatched = 0
        for instance in waiting_instances:
            try:
                definition = instance.flow_definition
                if not definition:
                    continue

                steps = definition.steps
                if instance.current_step >= len(steps):
                    continue

                step = steps[instance.current_step]

                if check_step_timeout(instance, step):
                    instance.status = "failed"
                    instance.error_message = f"Step timeout: {step['name']}"
                    instance.completed_at = datetime.now(timezone.utc)
                    session.flush()
                    logger.warning(f"Flow {instance.id} step '{step['name']}' timed out")
                    results.append({"instance_id": instance.id, "action": "timeout"})
                    continue

                advance_flow_task.delay(instance.id)
                dispatched += 1
                results.append({"instance_id": instance.id, "action": "dispatched"})
            except Exception as e:
                logger.exception(f"Error processing flow instance {instance.id}: {e}")
                results.append({"instance_id": instance.id, "action": "error", "error": str(e)})

        session.commit()
        return {
            "status": "ok",
            "checked": len(waiting_instances),
            "dispatched": dispatched,
            "results": results,
        }
    except Exception as e:
        session.rollback()
        logger.exception(f"poll_waiting_flows failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


@celery_app.task(name="flow.poll_crm_returns")
def poll_crm_returns():
    logger.info("poll_crm_returns started")
    SessionLocal = get_session_local()
    session = SessionLocal()
    connector = None
    try:
        flow_def = session.query(FlowDefinition).filter_by(name="crm_return_flow").first()
        if not flow_def:
            logger.warning("poll_crm_returns: flow definition 'crm_return_flow' not found")
            return {
                "status": "ok",
                "message": "flow definition not configured",
                "created": 0,
            }

        latest_instance = (
            session.query(FlowInstance)
            .filter(FlowInstance.flow_definition_id == flow_def.id)
            .order_by(FlowInstance.started_at.desc().nullslast(), FlowInstance.id.desc())
            .first()
        )
        since = (
            latest_instance.started_at
            if latest_instance and latest_instance.started_at
            else datetime.now(timezone.utc) - timedelta(hours=24)
        )

        return_entity = _extract_return_entity(flow_def)

        try:
            connector = get_connector_instance("fenxiangxiaoke", session)
        except Exception as e:
            logger.warning("poll_crm_returns: failed to get connector: %s", e)
            return {"status": "ok", "message": "connector not configured", "created": 0}

        try:
            records = connector.pull(return_entity, since=since)
        except Exception as e:
            logger.exception("poll_crm_returns: connector pull failed: %s", e)
            return {"status": "error", "error": str(e), "created": 0}

        if not records:
            logger.info(
                "poll_crm_returns completed: no records (entity=%s, since=%s)",
                return_entity,
                since,
            )
            return {
                "status": "ok",
                "flow_definition_id": flow_def.id,
                "entity": return_entity,
                "polled": 0,
                "created": 0,
            }

        existing_instances = (
            session.query(FlowInstance)
            .filter(
                FlowInstance.flow_definition_id == flow_def.id,
                FlowInstance.status.notin_(["cancelled"]),
            )
            .all()
        )
        processed_ids = set()
        for inst in existing_instances:
            ctx = inst.context or {}
            req = ctx.get("return_request", {}) if isinstance(ctx, dict) else {}
            if isinstance(req, dict):
                processed_id = _extract_record_id(req)
                if processed_id:
                    processed_ids.add(processed_id)

        created = 0
        skipped_existing = 0
        skipped_no_id = 0

        for record in records:
            if not isinstance(record, dict):
                logger.warning("poll_crm_returns: invalid CRM record type, skipping: %s", record)
                skipped_no_id += 1
                continue

            record_id = _extract_record_id(record)
            if not record_id:
                logger.warning(
                    "poll_crm_returns: CRM return record has no ID, skipping: %s", record
                )
                skipped_no_id += 1
                continue

            if record_id in processed_ids:
                skipped_existing += 1
                continue

            instance = create_instance(
                session,
                flow_def.id,
                context={"return_request": record},
            )
            processed_ids.add(record_id)
            created += 1
            advance_flow_task.delay(instance.id)

        session.commit()
        logger.info(
            "poll_crm_returns completed: created=%s skipped_existing=%s skipped_no_id=%s polled=%s",
            created,
            skipped_existing,
            skipped_no_id,
            len(records),
        )
        return {
            "status": "ok",
            "flow_definition_id": flow_def.id,
            "entity": return_entity,
            "since": since.isoformat() if isinstance(since, datetime) else str(since),
            "polled": len(records),
            "created": created,
            "skipped_existing": skipped_existing,
            "skipped_no_id": skipped_no_id,
        }
    except Exception as e:
        session.rollback()
        logger.exception("poll_crm_returns failed: %s", e)
        return {"status": "error", "error": str(e), "created": 0}
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                logger.warning("poll_crm_returns: failed to disconnect connector")
        session.close()
