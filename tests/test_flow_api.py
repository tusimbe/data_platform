import pytest

from src.models.flow import FlowDefinition, FlowInstance


@pytest.fixture
def flow_definition(db_session):
    definition = FlowDefinition(
        name="test_flow",
        description="Test",
        steps=[{"name": "s1", "action": "test_action", "timeout_minutes": 30}],
    )
    db_session.add(definition)
    db_session.flush()
    return definition


@pytest.fixture
def flow_instance(db_session, flow_definition):
    instance = FlowInstance(
        flow_definition_id=flow_definition.id,
        context={"test": True},
    )
    db_session.add(instance)
    db_session.flush()
    return instance


class TestFlowDefinitionAPI:
    def test_create_definition_success(self, client, api_headers):
        resp = client.post(
            "/api/v1/flows/definitions",
            json={
                "name": "api_flow_create",
                "description": "Test flow",
                "steps": [
                    {"name": "step1", "action": "test_action", "timeout_minutes": 30},
                    {"name": "step2", "action": "poll_test", "timeout_minutes": 60},
                ],
            },
            headers=api_headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["name"] == "api_flow_create"
        assert len(data["steps"]) == 2

    def test_create_definition_missing_fields(self, client, api_headers):
        resp = client.post(
            "/api/v1/flows/definitions",
            json={"name": "missing_steps"},
            headers=api_headers,
        )

        assert resp.status_code == 422

    def test_create_definition_requires_auth(self, client):
        resp = client.post(
            "/api/v1/flows/definitions",
            json={
                "name": "no_auth_flow",
                "description": "Test",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
        )

        assert resp.status_code == 401

    def test_list_definitions_empty(self, client, api_headers):
        resp = client.get("/api/v1/flows/definitions", headers=api_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_definitions_with_data(self, client, api_headers):
        client.post(
            "/api/v1/flows/definitions",
            json={
                "name": "list_flow_1",
                "description": "Test",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
            headers=api_headers,
        )

        resp = client.get("/api/v1/flows/definitions", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1

    def test_get_definition(self, client, api_headers):
        create_resp = client.post(
            "/api/v1/flows/definitions",
            json={
                "name": "detail_flow",
                "description": "Test",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
            headers=api_headers,
        )
        definition_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/flows/definitions/{definition_id}", headers=api_headers)

        assert resp.status_code == 200
        assert resp.json()["id"] == definition_id

    def test_get_definition_not_found(self, client, api_headers):
        resp = client.get("/api/v1/flows/definitions/99999", headers=api_headers)

        assert resp.status_code == 404

    def test_update_definition(self, client, api_headers):
        create_resp = client.post(
            "/api/v1/flows/definitions",
            json={
                "name": "update_flow_before",
                "description": "before",
                "steps": [{"name": "s1", "action": "test_action"}],
            },
            headers=api_headers,
        )
        definition_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/flows/definitions/{definition_id}",
            json={
                "name": "update_flow_after",
                "description": "after",
                "steps": [{"name": "s2", "action": "poll_test", "timeout_minutes": 15}],
            },
            headers=api_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "update_flow_after"
        assert data["description"] == "after"
        assert data["steps"][0]["action"] == "poll_test"


class TestFlowInstanceAPI:
    def test_list_instances_empty(self, client, api_headers):
        resp = client.get("/api/v1/flows/instances", headers=api_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_instances_filter_status(self, client, api_headers, db_session, flow_definition):
        pending_instance = FlowInstance(
            flow_definition_id=flow_definition.id, status="pending", context={}
        )
        failed_instance = FlowInstance(
            flow_definition_id=flow_definition.id, status="failed", context={}
        )
        db_session.add_all([pending_instance, failed_instance])
        db_session.flush()

        resp = client.get("/api/v1/flows/instances?status=pending", headers=api_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["status"] == "pending"

    def test_list_instances_filter_by_definition(self, client, api_headers, db_session):
        def1 = FlowDefinition(
            name="filter_def1",
            description="d1",
            steps=[{"name": "s1", "action": "test_action"}],
        )
        def2 = FlowDefinition(
            name="filter_def2",
            description="d2",
            steps=[{"name": "s1", "action": "test_action"}],
        )
        db_session.add_all([def1, def2])
        db_session.flush()

        db_session.add_all(
            [
                FlowInstance(flow_definition_id=def1.id, context={"a": 1}),
                FlowInstance(flow_definition_id=def2.id, context={"b": 2}),
            ]
        )
        db_session.flush()

        resp = client.get(
            f"/api/v1/flows/instances?flow_definition_id={def2.id}", headers=api_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["flow_definition_id"] == def2.id

    def test_get_instance(self, client, api_headers, flow_instance):
        resp = client.get(f"/api/v1/flows/instances/{flow_instance.id}", headers=api_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == flow_instance.id
        assert data["flow_definition_id"] == flow_instance.flow_definition_id

    def test_get_instance_not_found(self, client, api_headers):
        resp = client.get("/api/v1/flows/instances/99999", headers=api_headers)

        assert resp.status_code == 404

    def test_retry_instance(self, client, api_headers, db_session, flow_definition):
        failed_instance = FlowInstance(
            flow_definition_id=flow_definition.id,
            status="failed",
            retry_count=2,
            error_message="boom",
            context={},
        )
        db_session.add(failed_instance)
        db_session.flush()

        resp = client.post(
            f"/api/v1/flows/instances/{failed_instance.id}/retry", headers=api_headers
        )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["instance_id"] == failed_instance.id

    def test_retry_non_failed(self, client, api_headers, flow_instance):
        resp = client.post(f"/api/v1/flows/instances/{flow_instance.id}/retry", headers=api_headers)

        assert resp.status_code == 400

    def test_cancel_instance(self, client, api_headers, db_session, flow_definition):
        running_instance = FlowInstance(
            flow_definition_id=flow_definition.id,
            status="running",
            context={"x": 1},
        )
        db_session.add(running_instance)
        db_session.flush()

        resp = client.post(
            f"/api/v1/flows/instances/{running_instance.id}/cancel", headers=api_headers
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "cancelled"
        assert body["instance_id"] == running_instance.id

    def test_cancel_completed(self, client, api_headers, db_session, flow_definition):
        completed_instance = FlowInstance(
            flow_definition_id=flow_definition.id,
            status="completed",
            context={},
        )
        db_session.add(completed_instance)
        db_session.flush()

        resp = client.post(
            f"/api/v1/flows/instances/{completed_instance.id}/cancel", headers=api_headers
        )

        assert resp.status_code == 400
