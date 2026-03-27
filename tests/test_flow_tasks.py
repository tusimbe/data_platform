from unittest.mock import patch

from src.services.flow_service import create_definition, create_instance


class TestAdvanceFlowTaskChainDepth:
    def test_advance_flow_task_chain_depth_exceeded(self, db_session):
        definition = create_definition(
            db_session,
            {
                "name": "chain_depth_test",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
        )
        instance = create_instance(db_session, definition.id)
        instance.status = "running"
        db_session.flush()

        from src.tasks import flow_tasks

        with (
            patch("src.tasks.flow_tasks.get_session_local") as mock_gsl,
            patch.object(db_session, "close"),
        ):
            mock_gsl.return_value = lambda: db_session
            result = flow_tasks.advance_flow_task(instance.id, chain_depth=21)

        assert result["status"] == "failed"
        assert "Chain depth limit" in result["error"]
        assert instance.status == "failed"
        assert "Chain depth limit exceeded" in (instance.error_message or "")

    def test_advance_flow_task_normal_chain_depth(self, db_session):
        definition = create_definition(
            db_session,
            {
                "name": "chain_normal_test",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
        )
        instance = create_instance(db_session, definition.id)
        db_session.flush()

        from src.tasks import flow_tasks

        with (
            patch("src.tasks.flow_tasks.get_session_local") as mock_gsl,
            patch("src.tasks.flow_tasks.advance_flow") as mock_advance,
            patch.object(flow_tasks.advance_flow_task, "delay") as mock_delay,
            patch.object(db_session, "close"),
        ):
            mock_gsl.return_value = lambda: db_session
            mock_advance.return_value = {"status": "waiting"}
            result = flow_tasks.advance_flow_task(instance.id, chain_depth=5)

        assert result["status"] == "waiting"
        mock_delay.assert_not_called()


class TestPollWaitingFlows:
    def test_poll_waiting_flows_fanout_uses_delay_not_inline_advance(self, db_session):
        definition = create_definition(
            db_session,
            {
                "name": "poll_waiting_fanout_test",
                "steps": [{"name": "s1", "action": "test_action", "timeout_minutes": 30}],
            },
        )
        instance = create_instance(db_session, definition.id)
        instance.status = "waiting"
        db_session.flush()

        from src.tasks import flow_tasks

        with (
            patch("src.tasks.flow_tasks.get_session_local") as mock_gsl,
            patch("src.tasks.flow_tasks.check_step_timeout", return_value=False),
            patch.object(flow_tasks.advance_flow_task, "delay") as mock_delay,
            patch("src.tasks.flow_tasks.advance_flow") as mock_advance,
            patch.object(db_session, "close"),
        ):
            mock_gsl.return_value = lambda: db_session
            result = flow_tasks.poll_waiting_flows()

        assert result["status"] == "ok"
        assert result["checked"] == 1
        assert result["dispatched"] == 1
        assert result["results"][0]["action"] == "dispatched"
        mock_delay.assert_called_once_with(instance.id)
        mock_advance.assert_not_called()


class TestConnectorUtils:
    def test_get_connector_instance_import(self):
        from src.services.connector_utils import get_connector_instance

        assert callable(get_connector_instance)
