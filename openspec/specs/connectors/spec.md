# Connectors Specification

## Purpose

Define the behavior of the connector framework that integrates external business systems with the data platform. Each connector encapsulates the API interaction details of one external system and exposes a unified interface for data pull (inbound) and push (outbound).

## Requirements

### Requirement: Unified Connector Interface
The system SHALL provide an abstract base class that all connectors MUST implement, ensuring a consistent interface across different external systems.

#### Scenario: Connector implements required methods
- GIVEN a new connector class for an external system
- WHEN the connector is instantiated
- THEN it MUST implement: connect(), disconnect(), health_check(), list_entities(), pull(), push(), get_schema()
- AND failure to implement any required method results in a TypeError at import time

### Requirement: Connector Registration
The system SHALL maintain a registry of all available connectors, allowing dynamic lookup by connector type.

#### Scenario: Register a connector
- GIVEN a connector class decorated with @register_connector("kingdee_erp")
- WHEN the application starts
- THEN the connector is available in the registry under the key "kingdee_erp"

#### Scenario: Lookup a connector
- GIVEN a connector type string "fenxiangxiaoke"
- WHEN the registry is queried
- THEN the corresponding connector class is returned
- AND if the type is unknown, a ConnectorNotFoundError is raised

### Requirement: Connector Configuration
The system SHALL store connector configurations in the database, including connection parameters and authentication credentials.

#### Scenario: Create connector configuration
- GIVEN valid connector parameters (type, name, auth credentials, base URL)
- WHEN a connector configuration is saved
- THEN it is persisted in the connectors table
- AND authentication credentials are encrypted at rest

#### Scenario: Update connector configuration
- GIVEN an existing connector configuration
- WHEN the auth credentials are updated
- THEN the old credentials are replaced with new encrypted credentials
- AND the connector can authenticate with the new credentials on next sync

### Requirement: Health Check
The system MUST support health checking for each configured connector to verify connectivity.

#### Scenario: Healthy connector
- GIVEN a properly configured connector
- WHEN health_check() is called
- THEN it returns HealthStatus with status="healthy" and latency in milliseconds

#### Scenario: Unhealthy connector
- GIVEN a connector with invalid credentials
- WHEN health_check() is called
- THEN it returns HealthStatus with status="unhealthy" and an error message
- AND the error is logged

### Requirement: Data Pull (Inbound)
The system SHALL support pulling data from external systems, with both full and incremental modes.

#### Scenario: Full pull
- GIVEN a connector and an entity type (e.g., "sales_order")
- WHEN pull(entity="sales_order", since=None) is called
- THEN all records for that entity are returned as a list of dicts

#### Scenario: Incremental pull
- GIVEN a connector, an entity type, and a last sync timestamp
- WHEN pull(entity="sales_order", since=last_sync_time) is called
- THEN only records created or modified after last_sync_time are returned

#### Scenario: Pull with filters
- GIVEN additional filter parameters
- WHEN pull(entity="sales_order", filters={"status": "approved"}) is called
- THEN only records matching the filters are returned

#### Scenario: Pull failure
- GIVEN a connector that encounters an API error during pull
- WHEN the error occurs
- THEN a ConnectorPullError is raised with the original error details
- AND the error is logged with connector_id, entity, and timestamp

### Requirement: Data Push (Outbound)
The system SHALL support pushing data from the platform back to external systems.

#### Scenario: Successful push
- GIVEN a list of records to push to an external system
- WHEN push(entity="customer", records=[...]) is called
- THEN each record is created or updated in the external system
- AND a PushResult is returned with success_count and failure_count

#### Scenario: Partial push failure
- GIVEN a batch of records where some fail validation in the external system
- WHEN push() is called
- THEN successfully pushed records are committed
- AND failed records are reported in PushResult.failures with error details
- AND the sync continues (does not abort on individual record failure)

### Requirement: Entity Schema Discovery
The system SHOULD support discovering the field structure of entities from external systems.

#### Scenario: Get entity schema
- GIVEN a connector and an entity type
- WHEN get_schema(entity="customer") is called
- THEN an EntitySchema is returned containing field names, types, and required flags

### Requirement: Rate Limiting and Retry
The system MUST respect external API rate limits and implement retry with backoff.

#### Scenario: Rate limit hit
- GIVEN an external API returns a 429 (Too Many Requests) response
- WHEN the connector encounters this response
- THEN it waits for the duration specified in Retry-After header (or default backoff)
- AND retries the request up to 3 times

#### Scenario: Transient error retry
- GIVEN a transient network error (timeout, 502, 503)
- WHEN the connector encounters this error
- THEN it retries with exponential backoff (1s, 2s, 4s)
- AND after 3 failures, raises a ConnectorError

## Supported Connectors

### Requirement: Kingdee ERP Connector
The system SHALL provide a connector for Kingdee Cloud Constellation (金蝶云星空) via its Open API.

#### Scenario: Kingdee authentication
- GIVEN valid Kingdee API credentials (app_id, app_secret, acct_id)
- WHEN connect() is called
- THEN a session token is obtained and cached for subsequent requests

#### Scenario: Pull sales orders from Kingdee
- GIVEN a configured Kingdee ERP connector
- WHEN pull(entity="sales_order") is called
- THEN sales order data is retrieved via Kingdee Open API
- AND returned in the connector's standard dict format

### Requirement: Kingdee PLM Connector
The system SHALL provide a connector for Kingdee PLM via its API.

### Requirement: Fenxiangxiaoke CRM Connector
The system SHALL provide a connector for Fenxiangxiaoke (纷享销客) CRM via its Open Platform API.

### Requirement: Feishu Connector
The system SHALL provide a connector for Feishu (飞书) via its Open Platform API.

### Requirement: Zentao Connector
The system SHALL provide a connector for Zentao (禅道) via its REST API.

### Requirement: Lingxing ERP Connector
The system SHALL provide a connector for Lingxing (领星ERP) via its Open Platform API.
