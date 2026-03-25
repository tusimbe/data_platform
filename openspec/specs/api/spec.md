# API Specification

## Purpose

Define the REST API behavior of the data platform, providing unified data query, data write-back, connector management, and sync task management endpoints.

## Requirements

### Requirement: API Authentication
The system SHALL require authentication for all API endpoints.

#### Scenario: Valid API key
- GIVEN a request with a valid API key in the Authorization header
- WHEN any API endpoint is called
- THEN the request is processed normally

#### Scenario: Missing or invalid API key
- GIVEN a request without an API key or with an invalid one
- WHEN any API endpoint is called
- THEN a 401 Unauthorized response is returned
- AND the response body contains an error message

### Requirement: Unified Data Query
The system SHALL provide endpoints to query data from unified models with filtering, pagination, and sorting.

#### Scenario: List unified records
- GIVEN data exists in unified_customers
- WHEN GET /api/v1/data/customers is called
- THEN a paginated list of customer records is returned
- AND response includes total_count, page, page_size, and items

#### Scenario: Filter unified records
- GIVEN query parameters like ?source_system=fenxiangxiaoke&status=active
- WHEN GET /api/v1/data/customers is called with filters
- THEN only matching records are returned

#### Scenario: Get single record
- GIVEN a record ID
- WHEN GET /api/v1/data/customers/{id} is called
- THEN the full record is returned including source traceability fields

#### Scenario: Unknown entity type
- GIVEN an unsupported entity type
- WHEN GET /api/v1/data/unknown_entity is called
- THEN a 404 Not Found response is returned

### Requirement: Raw Data Query
The system SHALL provide endpoints to query raw (original) data by connector and entity.

#### Scenario: List raw records
- GIVEN raw data exists for kingdee_erp / sales_order
- WHEN GET /api/v1/raw/kingdee_erp/sales_order is called
- THEN raw JSONB records are returned with pagination

### Requirement: Data Write-Back
The system SHALL provide endpoints to push data from the platform to external systems.

#### Scenario: Push records to external system
- GIVEN a valid payload of records
- WHEN POST /api/v1/push/fenxiangxiaoke/customer is called
- THEN the connector pushes records to the external system
- AND response contains success_count and failure_count

#### Scenario: Push to unavailable system
- GIVEN the target system is down
- WHEN POST /api/v1/push/{connector}/{entity} is called
- THEN a 502 Bad Gateway response is returned
- AND error details are included in the response body

### Requirement: Connector Management
The system SHALL provide CRUD endpoints for connector configurations.

#### Scenario: List connectors
- WHEN GET /api/v1/connectors is called
- THEN all configured connectors are returned with their type, name, status (enabled/disabled), and last health check result
- AND auth credentials are NOT included in the response

#### Scenario: Create connector
- GIVEN valid connector parameters
- WHEN POST /api/v1/connectors is called
- THEN the connector configuration is created
- AND a 201 Created response is returned with the new connector's ID

#### Scenario: Update connector
- GIVEN an existing connector ID and updated parameters
- WHEN PUT /api/v1/connectors/{id} is called
- THEN the configuration is updated
- AND a 200 OK response is returned

#### Scenario: Delete connector
- GIVEN an existing connector ID
- WHEN DELETE /api/v1/connectors/{id} is called
- THEN the connector is soft-deleted (disabled, not removed)
- AND associated sync tasks are also disabled

### Requirement: Sync Task Management
The system SHALL provide endpoints to manage sync tasks and view sync logs.

#### Scenario: List sync tasks
- WHEN GET /api/v1/sync-tasks is called
- THEN all sync tasks are returned with their status, last run time, and next scheduled time

#### Scenario: Create sync task
- GIVEN valid parameters (connector_id, entity, direction, cron)
- WHEN POST /api/v1/sync-tasks is called
- THEN the sync task is created and scheduled

#### Scenario: Manually trigger sync
- GIVEN an existing sync task ID
- WHEN POST /api/v1/sync-tasks/{id}/trigger is called
- THEN the sync task is immediately enqueued for execution
- AND a 202 Accepted response is returned

#### Scenario: View sync logs
- WHEN GET /api/v1/sync-logs is called
- THEN sync execution logs are returned with pagination
- AND logs can be filtered by connector_id, entity, status, and date range

### Requirement: Health Check Endpoint
The system SHALL provide a health check endpoint.

#### Scenario: Platform healthy
- WHEN GET /api/v1/health is called
- THEN response includes:
  - database connectivity status
  - Redis connectivity status
  - Celery worker status
  - Overall status (healthy/degraded/unhealthy)

### Requirement: Standard Error Responses
The system SHALL return consistent error response format across all endpoints.

#### Scenario: Error response format
- GIVEN any API error occurs
- THEN the response body contains: {"error": {"code": "...", "message": "...", "details": ...}}
- AND appropriate HTTP status code is used (400, 401, 404, 409, 500, 502)

### Requirement: API Pagination
All list endpoints SHALL support cursor-based or offset pagination.

#### Scenario: Paginated response
- GIVEN a list endpoint
- WHEN called with ?page=2&page_size=20
- THEN the response returns items for page 2 with 20 items per page
- AND includes total_count for the full result set
