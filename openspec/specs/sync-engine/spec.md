# Sync Engine Specification

## Purpose

Define the behavior of the data synchronization engine that orchestrates pulling data from external systems, transforming it, storing it, and pushing data back to external systems on schedule.

## Requirements

### Requirement: Sync Task Configuration
The system SHALL allow defining sync tasks that specify which connector, entity, direction, and schedule to use.

#### Scenario: Create a pull sync task
- GIVEN a connector_id, entity type, and cron expression
- WHEN a sync task is created with direction="pull"
- THEN it is persisted in the sync_tasks table
- AND Celery Beat registers it for scheduled execution

#### Scenario: Create a push sync task
- GIVEN a connector_id, entity type, and cron expression
- WHEN a sync task is created with direction="push"
- THEN it is persisted in the sync_tasks table
- AND the task will push pending records from the platform to the external system

#### Scenario: Disable a sync task
- GIVEN an active sync task
- WHEN it is disabled
- THEN Celery Beat stops scheduling it
- AND its status is set to "disabled" in the database

### Requirement: Scheduled Execution
The system SHALL execute sync tasks on schedule using Celery Beat with cron expressions.

#### Scenario: Cron-triggered pull
- GIVEN a sync task configured with cron="0 */2 * * *" (every 2 hours)
- WHEN the cron fires
- THEN the sync task is enqueued as a Celery task
- AND it executes the pull flow for the configured connector and entity

#### Scenario: Manual trigger
- GIVEN an existing sync task
- WHEN a manual trigger is requested via API
- THEN the sync task is immediately enqueued
- AND it executes regardless of the cron schedule

### Requirement: Pull Sync Flow
The system SHALL implement a three-phase pull sync: fetch, transform, store.

#### Scenario: Successful pull sync
- GIVEN a pull sync task for connector=kingdee_erp, entity=sales_order
- WHEN the sync executes
- THEN Phase 1: connector.pull() fetches records from the external system
- AND Phase 2: field mappings are applied to transform data
- AND Phase 3: raw_data is upserted + unified table is upserted
- AND a sync_log is created with status="success", record counts, and timing

#### Scenario: Incremental pull sync
- GIVEN a sync task that has run before
- WHEN it runs again
- THEN it calls connector.pull(since=last_successful_sync_time)
- AND only new/modified records since the last sync are processed

#### Scenario: Pull sync with partial failures
- GIVEN a batch of pulled records where some fail transformation
- WHEN the sync processes records
- THEN successfully transformed records are stored normally
- AND failed records are logged in sync_log with error details
- AND the sync completes with status="partial_success"

### Requirement: Push Sync Flow
The system SHALL implement a three-phase push sync: read, transform, push.

#### Scenario: Successful push sync
- GIVEN a push sync task for connector=fenxiangxiaoke, entity=customer
- WHEN the sync executes
- THEN Phase 1: pending write-back records are read from the database
- AND Phase 2: reverse field mappings adapt data to target system format
- AND Phase 3: connector.push() sends records to the external system
- AND a sync_log is created with status and counts

#### Scenario: Push with write-back queue
- GIVEN records flagged for write-back in a pending_writes table
- WHEN a push sync executes
- THEN flagged records are picked up, pushed, and marked as completed
- AND failed records remain in pending state for retry

### Requirement: Sync Logging
The system MUST log every sync execution with detailed information.

#### Scenario: Sync log contents
- GIVEN a completed sync execution
- THEN the sync_log record contains:
  - sync_task_id
  - connector_id
  - entity
  - direction (pull/push)
  - started_at, finished_at
  - total_records, success_count, failure_count
  - status (success/partial_success/failure)
  - error_details (JSONB, for failed records)

#### Scenario: Query sync history
- GIVEN a connector_id or sync_task_id
- WHEN sync logs are queried
- THEN all matching logs are returned ordered by started_at descending
- AND logs can be filtered by status and date range

### Requirement: Error Handling and Recovery
The system MUST handle sync failures gracefully and support recovery.

#### Scenario: Connector unavailable
- GIVEN a connector whose external system is down
- WHEN a sync task tries to execute
- THEN the sync fails with a clear error message
- AND a sync_log is created with status="failure" and the error
- AND the next scheduled run will retry automatically

#### Scenario: Database write failure
- GIVEN a sync that successfully pulled data but fails during storage
- WHEN the database error occurs
- THEN the transaction is rolled back
- AND no partial data is committed
- AND the sync_log records the failure with error details

### Requirement: Concurrency Control
The system MUST prevent duplicate concurrent execution of the same sync task.

#### Scenario: Prevent duplicate execution
- GIVEN a sync task that is currently running
- WHEN the same task is triggered again (by schedule or manual)
- THEN the second execution is skipped
- AND a warning is logged
