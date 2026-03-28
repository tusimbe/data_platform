import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.core.exceptions import NotFoundError, ValidationError
from src.models.flow import FlowDefinition, FlowInstance, FlowStepAudit

logger = logging.getLogger(__name__)

MAX_RETRIES_PER_STEP = 3


@dataclass
class StepResult:
    status: str
    data: dict = field(default_factory=dict)
    error: str | None = None


STEP_HANDLERS: dict[str, Callable[[dict, "Session"], StepResult]] = {}


def check_step_timeout(instance: FlowInstance, step: dict) -> bool:
    timeout_minutes = step.get("timeout_minutes")
    if not timeout_minutes or not instance.updated_at:
        return False
    elapsed = (datetime.now(timezone.utc) - instance.updated_at).total_seconds() / 60
    return elapsed > timeout_minutes


def _query_instance_for_update(db: Session, instance_id: int) -> FlowInstance | None:
    query = db.query(FlowInstance).filter_by(id=instance_id)
    dialect_name = db.bind.dialect.name if db.bind else ""
    if dialect_name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    return query.first()


def advance_flow(instance_id: int, db: Session) -> dict:
    instance = _query_instance_for_update(db, instance_id)
    if not instance:
        raise NotFoundError(f"Flow instance {instance_id} not found")

    definition = db.query(FlowDefinition).filter_by(id=instance.flow_definition_id).first()
    if not definition:
        raise NotFoundError(f"Flow definition {instance.flow_definition_id} not found")

    if instance.status not in ("pending", "running", "waiting"):
        return {"status": instance.status, "message": "Flow is not advanceable"}

    steps = definition.steps
    if instance.current_step >= len(steps):
        instance.status = "completed"
        instance.completed_at = datetime.now(timezone.utc)
        db.flush()
        return {"status": "completed"}

    step = steps[instance.current_step]
    action = step["action"]
    handler = STEP_HANDLERS.get(action)
    if not handler:
        instance.status = "failed"
        instance.error_message = f"No handler registered for action: {action}"
        db.flush()
        return {"status": "failed", "error": instance.error_message}

    if instance.status == "pending":
        instance.started_at = datetime.now(timezone.utc)
    instance.status = "running"

    audit = FlowStepAudit(
        flow_instance_id=instance.id,
        step_index=instance.current_step,
        action=action,
        status="started",
        attempt=instance.retry_count + 1,
        started_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.flush()

    try:
        result = handler(instance.context, db)
    except Exception as e:
        logger.exception(
            "Flow step handler execution error",
            extra={
                "flow_instance_id": instance_id,
                "step_name": step["name"],
                "error": str(e),
            },
        )
        result = StepResult(status="failed", error=str(e))

    if result.status == "completed":
        audit.status = "completed"
        audit.completed_at = datetime.now(timezone.utc)
        audit.step_data = result.data
        new_context = {**instance.context, **result.data}
        try:
            context_size = len(json.dumps(new_context))
            if context_size > 1_000_000:
                logger.warning(
                    "Flow context size exceeds 1MB warning threshold",
                    extra={
                        "flow_instance_id": instance_id,
                        "context_size_bytes": context_size,
                        "warning_threshold_bytes": 1_000_000,
                    },
                )
        except (TypeError, ValueError):
            pass
        instance.context = new_context
        instance.retry_count = 0
        instance.current_step += 1

        if instance.current_step >= len(steps):
            instance.status = "completed"
            instance.completed_at = datetime.now(timezone.utc)
            logger.info(
                "Flow completed all steps",
                extra={
                    "flow_instance_id": instance_id,
                    "total_steps": len(steps),
                },
            )
        else:
            next_step = steps[instance.current_step]
            if next_step["action"].startswith("poll_"):
                instance.status = "waiting"
            else:
                instance.status = "running"
        db.flush()
        return {"status": instance.status, "current_step": instance.current_step}

    if result.status == "waiting":
        audit.status = "waiting"
        audit.completed_at = datetime.now(timezone.utc)
        instance.status = "waiting"
        db.flush()
        return {"status": "waiting", "current_step": instance.current_step}

    if result.status == "cancelled":
        audit.status = "cancelled"
        audit.completed_at = datetime.now(timezone.utc)
        audit.error_message = result.error
        instance.status = "cancelled"
        instance.error_message = result.error
        instance.completed_at = datetime.now(timezone.utc)
        db.flush()
        logger.info(
            "Flow cancelled at step",
            extra={
                "flow_instance_id": instance_id,
                "step_name": step["name"],
                "cancel_reason": result.error,
            },
        )
        return {"status": "cancelled", "reason": result.error}

    if result.status == "failed":
        audit.status = "failed"
        audit.completed_at = datetime.now(timezone.utc)
        audit.error_message = result.error
        instance.retry_count += 1
        instance.error_message = result.error
        if instance.retry_count >= MAX_RETRIES_PER_STEP:
            instance.status = "failed"
            logger.error(
                "Flow step failed after max retries",
                extra={
                    "flow_instance_id": instance_id,
                    "step_name": step["name"],
                    "retry_count": instance.retry_count,
                    "max_retries": MAX_RETRIES_PER_STEP,
                },
            )
        else:
            instance.status = "running"
            logger.warning(
                "Flow step failed and will retry",
                extra={
                    "flow_instance_id": instance_id,
                    "step_name": step["name"],
                    "retry_count": instance.retry_count,
                    "max_retries": MAX_RETRIES_PER_STEP,
                },
            )
        db.flush()
        return {
            "status": instance.status,
            "error": result.error,
            "retry_count": instance.retry_count,
        }

    instance.status = "failed"
    instance.error_message = f"Unknown step result status: {result.status}"
    audit.status = "failed"
    audit.completed_at = datetime.now(timezone.utc)
    audit.error_message = instance.error_message
    db.flush()
    return {"status": "failed", "error": instance.error_message}


def create_definition(db: Session, data: dict) -> FlowDefinition:
    definition = FlowDefinition(
        name=data["name"],
        description=data.get("description"),
        steps=data["steps"],
    )
    db.add(definition)
    db.flush()
    return definition


def list_definitions(db: Session, params: PaginationParams) -> dict:
    query = db.query(FlowDefinition).order_by(FlowDefinition.id)
    return paginate(query, params)


def get_definition(db: Session, definition_id: int) -> FlowDefinition:
    definition = db.query(FlowDefinition).filter_by(id=definition_id).first()
    if not definition:
        raise NotFoundError(f"Flow definition {definition_id} not found")
    return definition


def update_definition(db: Session, definition_id: int, data: dict) -> FlowDefinition:
    definition = get_definition(db, definition_id)
    for key, value in data.items():
        if value is not None and hasattr(definition, key):
            setattr(definition, key, value)
    db.flush()
    return definition


def create_instance(
    db: Session,
    flow_definition_id: int,
    context: dict | None = None,
    source_record_id: str | None = None,
) -> FlowInstance:
    get_definition(db, flow_definition_id)
    instance = FlowInstance(
        flow_definition_id=flow_definition_id,
        context=context or {},
        source_record_id=source_record_id,
    )
    db.add(instance)
    db.flush()
    return instance


def instance_exists_for_source(
    db: Session,
    flow_definition_id: int,
    source_record_id: str,
) -> bool:
    return (
        db.query(FlowInstance)
        .filter(
            FlowInstance.flow_definition_id == flow_definition_id,
            FlowInstance.source_record_id == source_record_id,
            FlowInstance.status.notin_(["cancelled"]),
        )
        .first()
        is not None
    )


def list_instances(
    db: Session,
    params: PaginationParams,
    status: str | None = None,
    flow_definition_id: int | None = None,
) -> dict:
    query = db.query(FlowInstance).order_by(FlowInstance.id.desc())
    if status:
        query = query.filter(FlowInstance.status == status)
    if flow_definition_id:
        query = query.filter(FlowInstance.flow_definition_id == flow_definition_id)
    return paginate(query, params)


def get_instance(db: Session, instance_id: int) -> FlowInstance:
    instance = db.query(FlowInstance).filter_by(id=instance_id).first()
    if not instance:
        raise NotFoundError(f"Flow instance {instance_id} not found")
    return instance


def retry_instance(db: Session, instance_id: int) -> FlowInstance:
    instance = get_instance(db, instance_id)
    if instance.status != "failed":
        raise ValidationError("Can only retry failed instances")
    instance.retry_count = 0
    instance.status = "running"
    instance.error_message = None
    db.flush()
    return instance


def cancel_instance(db: Session, instance_id: int) -> FlowInstance:
    instance = get_instance(db, instance_id)
    if instance.status in ("completed", "cancelled"):
        raise ValidationError(f"Cannot cancel instance in '{instance.status}' status")
    instance.status = "cancelled"
    instance.completed_at = datetime.now(timezone.utc)
    db.flush()
    return instance


def _register_flow_step_handlers() -> None:
    from src.handlers.flow_steps import STEP_HANDLERS as _FLOW_STEP_HANDLERS

    STEP_HANDLERS.update(_FLOW_STEP_HANDLERS)


_register_flow_step_handlers()
