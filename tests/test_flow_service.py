from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.api.deps import PaginationParams
from src.core.exceptions import NotFoundError, ValidationError
from src.models.flow import FlowStepAudit
from src.services.flow_service import (
    MAX_RETRIES_PER_STEP,
    STEP_HANDLERS,
    StepResult,
    _query_instance_for_update,
    advance_flow,
    cancel_instance,
    check_step_timeout,
    create_definition,
    create_instance,
    get_definition,
    get_instance,
    instance_exists_for_source,
    list_definitions,
    list_instances,
    retry_instance,
    update_definition,
)


def _completed_handler(context, db):
    return StepResult(status="completed", data={"handler_output": "test"})


def _waiting_handler(context, db):
    return StepResult(status="waiting")


def _failed_handler(context, db):
    return StepResult(status="failed", error="test error")


def _cancelled_handler(context, db):
    return StepResult(status="cancelled", error="Approval REJECTED")


def _make_definition(db_session, name="flow_a", steps=None):
    return create_definition(
        db_session,
        {
            "name": name,
            "description": "desc",
            "steps": steps
            or [
                {"name": "step1", "action": "test_action", "timeout_minutes": 30},
            ],
        },
    )


class TestFlowDefinitionService:
    def test_create_definition(self, db_session):
        definition = create_definition(
            db_session,
            {
                "name": "test_flow",
                "description": "Test flow",
                "steps": [{"name": "step1", "action": "test_action", "timeout_minutes": 30}],
            },
        )

        assert definition.id is not None
        assert definition.name == "test_flow"
        assert definition.steps[0]["action"] == "test_action"

    def test_create_definition_unique_name(self, db_session):
        create_definition(
            db_session,
            {
                "name": "dup_flow",
                "description": "d1",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
        )

        with pytest.raises(IntegrityError):
            create_definition(
                db_session,
                {
                    "name": "dup_flow",
                    "description": "d2",
                    "steps": [{"name": "s2", "action": "test_action"}],
                },
            )

    def test_get_definition_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            get_definition(db_session, 99999)

    def test_update_definition(self, db_session):
        definition = _make_definition(db_session, name="before_name")

        updated = update_definition(
            db_session,
            definition.id,
            {
                "name": "after_name",
                "description": "updated",
                "steps": [{"name": "new", "action": "new_action", "timeout_minutes": 10}],
            },
        )

        assert updated.name == "after_name"
        assert updated.description == "updated"
        assert updated.steps[0]["action"] == "new_action"

    def test_list_definitions(self, db_session):
        _make_definition(db_session, name="flow_1")
        _make_definition(db_session, name="flow_2")

        result = list_definitions(db_session, PaginationParams(page=1, page_size=10))

        assert "items" in result
        assert result["total_count"] == 2
        assert len(result["items"]) == 2


class TestFlowInstanceService:
    def test_create_instance(self, db_session):
        definition = _make_definition(db_session, name="instance_base")

        instance = create_instance(db_session, definition.id)

        assert instance.id is not None
        assert instance.flow_definition_id == definition.id
        assert instance.status == "pending"
        assert instance.current_step == 0

    def test_create_instance_with_context(self, db_session):
        definition = _make_definition(db_session, name="instance_ctx")

        instance = create_instance(db_session, definition.id, context={"foo": "bar"})

        assert instance.context == {"foo": "bar"}

    def test_create_instance_with_source_record_id(self, db_session):
        definition = _make_definition(db_session, name="instance_source_record")

        instance = create_instance(
            db_session,
            definition.id,
            context={"foo": "bar"},
            source_record_id="crm-123",
        )

        assert instance.source_record_id == "crm-123"

    def test_instance_exists_for_source(self, db_session):
        definition = _make_definition(db_session, name="exists_source_record")

        create_instance(
            db_session,
            definition.id,
            context={"return_request": {"_id": "crm-1"}},
            source_record_id="crm-1",
        )

        assert instance_exists_for_source(db_session, definition.id, "crm-1") is True
        assert instance_exists_for_source(db_session, definition.id, "crm-2") is False

    def test_create_instance_invalid_definition(self, db_session):
        with pytest.raises(NotFoundError):
            create_instance(db_session, 99999)

    def test_get_instance_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            get_instance(db_session, 99999)

    def test_list_instances_filter_by_status(self, db_session):
        definition = _make_definition(db_session, name="filter_status")
        create_instance(db_session, definition.id)
        failed = create_instance(db_session, definition.id)
        failed.status = "failed"
        db_session.flush()

        result = list_instances(
            db_session,
            PaginationParams(page=1, page_size=20),
            status="failed",
            flow_definition_id=None,
        )

        assert result["total_count"] == 1
        assert result["items"][0].status == "failed"

    def test_list_instances_filter_by_definition(self, db_session):
        definition_a = _make_definition(db_session, name="filter_def_a")
        definition_b = _make_definition(db_session, name="filter_def_b")
        create_instance(db_session, definition_a.id)
        create_instance(db_session, definition_b.id)

        result = list_instances(
            db_session,
            PaginationParams(page=1, page_size=20),
            status=None,
            flow_definition_id=definition_b.id,
        )

        assert result["total_count"] == 1
        assert result["items"][0].flow_definition_id == definition_b.id


class TestAdvanceFlowStateMachine:
    def test_advance_flow_creates_audit_record(self, db_session):
        definition = _make_definition(db_session, name="adv_audit_completed")
        instance = create_instance(db_session, definition.id, context={"seed": 1})

        with patch.dict(STEP_HANDLERS, {"test_action": _completed_handler}):
            result = advance_flow(instance.id, db_session)

        audit_records = (
            db_session.query(FlowStepAudit)
            .filter(FlowStepAudit.flow_instance_id == instance.id)
            .order_by(FlowStepAudit.id)
            .all()
        )
        assert result["status"] == "completed"
        assert len(audit_records) == 1
        assert audit_records[0].step_index == 0
        assert audit_records[0].action == "test_action"
        assert audit_records[0].status == "completed"
        assert audit_records[0].attempt == 1
        assert audit_records[0].started_at is not None
        assert audit_records[0].completed_at is not None
        assert audit_records[0].step_data == {"handler_output": "test"}

    def test_advance_flow_audit_records_failure(self, db_session):
        definition = _make_definition(db_session, name="adv_audit_failed")
        instance = create_instance(db_session, definition.id)

        with patch.dict(STEP_HANDLERS, {"test_action": _failed_handler}):
            result = advance_flow(instance.id, db_session)

        audit_record = (
            db_session.query(FlowStepAudit)
            .filter(FlowStepAudit.flow_instance_id == instance.id)
            .order_by(FlowStepAudit.id)
            .first()
        )
        assert result["status"] == "running"
        assert audit_record is not None
        assert audit_record.status == "failed"
        assert audit_record.error_message == "test error"
        assert audit_record.step_data is None
        assert audit_record.completed_at is not None

    def test_advance_flow_audit_records_multiple_steps(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_audit_multi",
            steps=[
                {"name": "s1", "action": "step_one"},
                {"name": "s2", "action": "step_two"},
                {"name": "s3", "action": "step_three"},
            ],
        )
        instance = create_instance(db_session, definition.id)

        with patch.dict(
            STEP_HANDLERS,
            {
                "step_one": lambda context, db: StepResult(status="completed", data={"a": 1}),
                "step_two": lambda context, db: StepResult(status="completed", data={"b": 2}),
                "step_three": lambda context, db: StepResult(status="completed", data={"c": 3}),
            },
        ):
            for _ in range(3):
                advance_flow(instance.id, db_session)

        audit_records = (
            db_session.query(FlowStepAudit)
            .filter(FlowStepAudit.flow_instance_id == instance.id)
            .order_by(FlowStepAudit.id)
            .all()
        )
        assert len(audit_records) == 3
        assert [audit.step_index for audit in audit_records] == [0, 1, 2]
        assert [audit.status for audit in audit_records] == ["completed", "completed", "completed"]

    def test_advance_flow_completed_step(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_completed",
            steps=[
                {"name": "s1", "action": "test_action"},
                {"name": "s2", "action": "next_action"},
            ],
        )
        instance = create_instance(db_session, definition.id, context={"seed": 1})

        with patch.dict(STEP_HANDLERS, {"test_action": _completed_handler}):
            result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "running"
        assert refreshed.current_step == 1
        assert refreshed.context["handler_output"] == "test"
        assert refreshed.started_at is not None

    def test_advance_flow_waiting_step(self, db_session):
        definition = _make_definition(db_session, name="adv_waiting")
        instance = create_instance(db_session, definition.id)

        with patch.dict(STEP_HANDLERS, {"test_action": _waiting_handler}):
            result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "waiting"
        assert refreshed.status == "waiting"
        assert refreshed.current_step == 0

    def test_advance_flow_failed_step_retries(self, db_session):
        definition = _make_definition(db_session, name="adv_failed_retries")
        instance = create_instance(db_session, definition.id)

        with patch.dict(STEP_HANDLERS, {"test_action": _failed_handler}):
            result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "running"
        assert result["retry_count"] == 1
        assert refreshed.retry_count == 1
        assert refreshed.status == "running"

    def test_advance_flow_failed_max_retries(self, db_session):
        definition = _make_definition(db_session, name="adv_failed_max")
        instance = create_instance(db_session, definition.id)

        with patch.dict(STEP_HANDLERS, {"test_action": _failed_handler}):
            result = {}
            for _ in range(MAX_RETRIES_PER_STEP):
                result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "failed"
        assert refreshed.status == "failed"
        assert refreshed.retry_count == MAX_RETRIES_PER_STEP
        assert refreshed.error_message == "test error"

    def test_advance_flow_no_handler(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_no_handler",
            steps=[{"name": "s1", "action": "unknown_action"}],
        )
        instance = create_instance(db_session, definition.id)

        result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "failed"
        assert "No handler registered" in result["error"]
        assert refreshed.status == "failed"

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
    def test_advance_flow_not_advanceable(self, db_session, status):
        definition = _make_definition(db_session, name=f"adv_not_{status}")
        instance = create_instance(db_session, definition.id)
        instance.status = status
        db_session.flush()

        result = advance_flow(instance.id, db_session)

        assert result["status"] == status
        assert result["message"] == "Flow is not advanceable"

    def test_advance_flow_completes_all_steps(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_complete_all",
            steps=[
                {"name": "s1", "action": "step_one"},
                {"name": "s2", "action": "step_two"},
            ],
        )
        instance = create_instance(db_session, definition.id)

        with patch.dict(
            STEP_HANDLERS,
            {
                "step_one": lambda context, db: StepResult(status="completed", data={"a": 1}),
                "step_two": lambda context, db: StepResult(status="completed", data={"b": 2}),
            },
        ):
            first = advance_flow(instance.id, db_session)
            second = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert first["status"] == "running"
        assert second["status"] == "completed"
        assert refreshed.status == "completed"
        assert refreshed.current_step == 2
        assert refreshed.completed_at is not None

    def test_advance_flow_context_accumulates(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_ctx",
            steps=[
                {"name": "s1", "action": "ctx_one"},
                {"name": "s2", "action": "ctx_two"},
            ],
        )
        instance = create_instance(db_session, definition.id, context={"seed": 0})

        with patch.dict(
            STEP_HANDLERS,
            {
                "ctx_one": lambda context, db: StepResult(status="completed", data={"x": 1}),
                "ctx_two": lambda context, db: StepResult(status="completed", data={"y": 2}),
            },
        ):
            advance_flow(instance.id, db_session)
            advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert refreshed.context == {"seed": 0, "x": 1, "y": 2}

    def test_advance_flow_next_step_poll_sets_waiting(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_poll_waiting",
            steps=[
                {"name": "s1", "action": "test_action"},
                {"name": "s2", "action": "poll_test"},
            ],
        )
        instance = create_instance(db_session, definition.id)

        with patch.dict(
            STEP_HANDLERS, {"test_action": _completed_handler, "poll_test": _waiting_handler}
        ):
            result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "waiting"
        assert refreshed.status == "waiting"
        assert refreshed.current_step == 1

    def test_advance_flow_cancelled_result(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_cancelled",
            steps=[{"name": "s1", "action": "cancel_action"}],
        )
        instance = create_instance(db_session, definition.id)

        with patch.dict(STEP_HANDLERS, {"cancel_action": _cancelled_handler}):
            result = advance_flow(instance.id, db_session)

        refreshed = get_instance(db_session, instance.id)
        assert result["status"] == "cancelled"
        assert result["reason"] == "Approval REJECTED"
        assert refreshed.status == "cancelled"
        assert refreshed.error_message == "Approval REJECTED"
        assert refreshed.completed_at is not None

    def test_advance_flow_logs_warning_when_context_exceeds_threshold(self, db_session):
        definition = _make_definition(
            db_session,
            name="adv_context_warning",
            steps=[{"name": "s1", "action": "large_context_action"}],
        )
        instance = create_instance(
            db_session,
            definition.id,
            context={"existing": "x" * 1_000_100},
        )

        with patch.dict(
            STEP_HANDLERS,
            {
                "large_context_action": lambda context, db: StepResult(
                    status="completed",
                    data={"more": "y"},
                )
            },
        ):
            with patch("src.services.flow_service.logger") as mock_logger:
                advance_flow(instance.id, db_session)

        assert mock_logger.warning.called
        warning_call_args = mock_logger.warning.call_args[0][0]
        assert "exceeds 1MB warning threshold" in warning_call_args


class TestFlowTimeoutAndLifecycle:
    def test_check_step_timeout_not_expired(self, db_session):
        definition = _make_definition(db_session, name="timeout_not_expired")
        instance = create_instance(db_session, definition.id)
        instance.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        assert check_step_timeout(instance, {"timeout_minutes": 30}) is False

    def test_check_step_timeout_expired(self, db_session):
        definition = _make_definition(db_session, name="timeout_expired")
        instance = create_instance(db_session, definition.id)
        instance.updated_at = datetime.now(timezone.utc) - timedelta(minutes=31)

        assert check_step_timeout(instance, {"timeout_minutes": 30}) is True

    def test_check_step_timeout_no_timeout_configured(self, db_session):
        definition = _make_definition(db_session, name="timeout_none")
        instance = create_instance(db_session, definition.id)
        instance.updated_at = datetime.now(timezone.utc) - timedelta(minutes=120)

        assert check_step_timeout(instance, {"name": "s1", "action": "a"}) is False

    def test_retry_instance(self, db_session):
        definition = _make_definition(db_session, name="retry_ok")
        instance = create_instance(db_session, definition.id)
        instance.status = "failed"
        instance.retry_count = 2
        instance.error_message = "boom"
        db_session.flush()

        retried = retry_instance(db_session, instance.id)

        assert retried.status == "running"
        assert retried.retry_count == 0
        assert retried.error_message is None

    def test_retry_non_failed(self, db_session):
        definition = _make_definition(db_session, name="retry_invalid")
        instance = create_instance(db_session, definition.id)

        with pytest.raises(ValidationError):
            retry_instance(db_session, instance.id)

    def test_cancel_instance(self, db_session):
        definition = _make_definition(db_session, name="cancel_ok")
        instance = create_instance(db_session, definition.id)
        instance.status = "running"
        db_session.flush()

        cancelled = cancel_instance(db_session, instance.id)

        assert cancelled.status == "cancelled"
        assert cancelled.completed_at is not None

    def test_cancel_completed(self, db_session):
        definition = _make_definition(db_session, name="cancel_invalid")
        instance = create_instance(db_session, definition.id)
        instance.status = "completed"
        db_session.flush()

        with pytest.raises(ValidationError):
            cancel_instance(db_session, instance.id)


class TestFlowQueryInstanceForUpdate:
    def test_query_instance_for_update_returns_instance_on_sqlite(self, db_session):
        definition = _make_definition(db_session, name="query_for_update")
        instance = create_instance(db_session, definition.id)

        queried = _query_instance_for_update(db_session, instance.id)

        assert queried is not None
        assert queried.id == instance.id
