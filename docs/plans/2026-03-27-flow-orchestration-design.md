# Flow Orchestration Engine — Design Document

**Date**: 2026-03-27
**Status**: Approved
**Author**: AI Assistant + User collaborative design

## Overview

A state machine-based flow orchestration engine that automates multi-step business processes across CRM, OA, and ERP systems. The first flow implements:

**CRM退货申请 → 飞书OA审批 → ERP退货单 → ERP负向应收单 → ERP收款退款单 → 通知财务 → 通知销售**

## Architecture Decision

**Chosen: State Machine + Celery Tasks** (over Celery Canvas chains and DAG engines)

Rationale:
- Reuses existing infrastructure (Celery + Postgres + Redis)
- Zero new dependencies
- "Wait for external event" pattern maps naturally to state machine + Celery Beat polling
- Simple enough for sequential flows, extensible for future business flows

## Data Model

### `flow_definitions` — Flow Templates

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | |
| `name` | String(100) | Unique flow type name (e.g., "crm_return_flow") |
| `description` | Text | Human-readable description |
| `steps` | JSON | Ordered list of step definitions |
| `created_at` | DateTime | |

Steps JSON structure:
```json
[
  {"name": "create_feishu_approval", "action": "create_feishu_approval", "timeout_minutes": 30},
  {"name": "wait_feishu_approval", "action": "poll_feishu_approval", "timeout_minutes": 20160},
  {"name": "create_erp_return_order", "action": "create_erp_return_order", "timeout_minutes": 30},
  {"name": "create_erp_negative_receivable", "action": "create_erp_negative_receivable", "timeout_minutes": 30},
  {"name": "create_erp_refund_bill", "action": "create_erp_refund_bill", "timeout_minutes": 30},
  {"name": "notify_finance", "action": "notify_finance", "timeout_minutes": 10},
  {"name": "notify_sales", "action": "notify_sales", "timeout_minutes": 10}
]
```

### `flow_instances` — Flow Instances

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | |
| `flow_definition_id` | FK → flow_definitions | |
| `current_step` | Integer | Index into steps array (0-based) |
| `status` | String(20) | `pending`, `running`, `waiting`, `completed`, `failed`, `cancelled` |
| `context` | JSON | Accumulated data from each step |
| `error_message` | Text | Last error if failed |
| `retry_count` | Integer | Per-step retry count, resets on advance |
| `started_at` | DateTime | |
| `updated_at` | DateTime | |
| `completed_at` | DateTime | |

## State Machine

### Status Transitions

```
[pending] → [running] → [waiting] → [running] → ... → [completed]
                ↓            ↓
            [failed]     [failed]
                ↓            ↓
            [running] (manual retry)

Any state → [cancelled] (manual cancel or approval rejected)
```

### Execution Logic

Core method `advance_flow(instance_id)`:

1. Load instance + definition
2. Get current step from definition
3. Dispatch to registered step handler
4. Handler returns one of: `completed` (with data), `waiting`, `failed` (with error)
5. On `completed`: merge output into context, advance to next step
   - If next step is a poll/wait action → set status to `waiting`
   - If next step is instant → set status to `running`, immediately execute
   - If no more steps → set status to `completed`
6. On `waiting`: stay on current step, will be polled by Celery Beat
7. On `failed`: increment retry_count. If >= 3, set status to `failed`

### Celery Tasks

1. **`advance_flow_task(instance_id)`** — Executes the next step. For non-waiting steps, chains to itself for the next step.

2. **`poll_waiting_flows()`** — Celery Beat, every 5 minutes. Queries all `status='waiting'` instances, calls `advance_flow()` on each.

3. **`poll_crm_returns()`** — Celery Beat, every 5 minutes. Polls CRM for new return requests, creates FlowInstance for each new one.

## Polling Details

### Polling Point 1: CRM Return Request Detection (Flow Trigger)

- Celery Beat every 5 minutes
- Calls 纷享销客 CRM API for recent return requests
- Filters out already-processed requests (matched against existing FlowInstances)
- Each new request → new FlowInstance with return data in context → immediate advance

### Polling Point 2: Feishu Approval Status (Flow Step)

- Part of `poll_waiting_flows()` Celery Beat task
- Calls Feishu `GET /open-apis/approval/v4/instances/{instance_code}`
- APPROVED → advance to next step
- REJECTED/CANCELED → mark flow as `cancelled`
- PENDING → stay in `waiting`
- Timeout: **2 weeks (20160 minutes)**

### Steps 4-8: Instant Execution (No Polling)

All ERP document creation and notification steps execute immediately via API calls.

## Step Handlers

### Registry

```python
STEP_HANDLERS = {
    "create_feishu_approval": create_feishu_approval_handler,
    "poll_feishu_approval": poll_feishu_approval_handler,
    "create_erp_return_order": create_erp_return_order_handler,
    "create_erp_negative_receivable": create_erp_negative_receivable_handler,
    "create_erp_refund_bill": create_erp_refund_bill_handler,
    "notify_finance": notify_finance_handler,
    "notify_sales": notify_sales_handler,
}
```

### Step Details

| Step | Action | Input (from context) | Output (to context) | API |
|------|--------|---------------------|---------------------|-----|
| 1 | `create_feishu_approval` | Return request data | `approval_instance_code` | Feishu POST /approval/v4/instances |
| 2 | `poll_feishu_approval` | `approval_instance_code` | Approver info, status | Feishu GET /approval/v4/instances/{code} |
| 3 | `create_erp_return_order` | Return data + approval | `return_order_bill_no` | Kingdee SAL_RETURNSTOCK Save→Submit→Audit |
| 4 | `create_erp_negative_receivable` | `return_order_bill_no` | `receivable_bill_no` | Kingdee AR_RECEIVABLE Save→Submit→Audit |
| 5 | `create_erp_refund_bill` | `receivable_bill_no` | `refund_bill_no` | Kingdee AR_REFUNDBILL Save→Submit→Audit |
| 6 | `notify_finance` | All bill numbers | notification_sent flag | Feishu POST /im/v1/messages |
| 7 | `notify_sales` | All bill numbers + applicant | notification_sent flag | Feishu POST /im/v1/messages |

## Multi-Flow Support

### Design Principles

- **FlowDefinition per flow type**: Each business flow is a row in `flow_definitions`
- **Reusable handlers**: Different flows can reference the same handler (e.g., multiple flows use `create_feishu_approval`)
- **Steps in JSON**: Adjustable via API without code changes
- **Context schema per handler**: Each handler declares its own input/output contract

### Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/flows/definitions` | GET | List all flow templates |
| `/flows/definitions` | POST | Create new flow template |
| `/flows/definitions/{id}` | PUT | Update flow template |
| `/flows/instances` | GET | List instances (filter by status/flow type) |
| `/flows/instances/{id}` | GET | Instance detail (current step, context, errors) |
| `/flows/instances/{id}/retry` | POST | Retry failed step (reset retry_count) |
| `/flows/instances/{id}/cancel` | POST | Cancel instance |

### Not Implemented (YAGNI)

- Visual drag-and-drop flow editor
- Conditional branching / parallel steps
- Dynamic handler loading (handlers are Python code, registered at import)

## Error Handling

### Per-Step Retry

- Max 3 retries per step (configurable in step definition)
- Instant steps retry immediately; polling steps retry on next poll cycle
- Retry count resets when advancing to next step

### Error Classification

| Error Type | Behavior |
|-----------|----------|
| Network timeout / 5xx | Auto-retry (recoverable) |
| Auth failure (401/403) | Mark failed, needs manual intervention |
| Business rejection (API error) | Mark failed, log API error response |
| Approval rejected (REJECTED) | Mark `cancelled` (normal business outcome) |
| Step timeout | Mark failed, error = "step timeout: {step_name}" |

### Manual Intervention

- `POST /flows/instances/{id}/retry` — Reset retry_count, re-execute current step
- `POST /flows/instances/{id}/cancel` — Cancel from any state

## Observability

- `FlowInstance.context` JSON = audit trail (all step outputs)
- `status` + `current_step` = real-time progress
- `error_message` = failure reason
- `updated_at` = last activity
- Logger output: flow_instance_id, step_name, duration per step

## File Structure

```
src/
├── models/
│   └── flow.py                    # NEW: FlowDefinition, FlowInstance
├── services/
│   └── flow_service.py            # NEW: FlowExecutor (advance_flow, state machine)
├── tasks/
│   └── flow_tasks.py              # NEW: advance_flow_task, poll_waiting_flows, poll_crm_returns
├── api/routes/
│   └── flows.py                   # NEW: Flow CRUD + instance management
├── connectors/
│   ├── feishu.py                  # MODIFY: add create_approval_instance(), send_message()
│   └── kingdee_erp.py             # MODIFY: add submit(), audit(), new FormIDs
├── handlers/
│   └── flow_steps.py              # NEW: 8 step handler functions + STEP_HANDLERS registry
└── core/
    └── celery_app.py              # MODIFY: register flow_tasks module

alembic/versions/
    └── xxx_add_flow_tables.py     # NEW: migration
```

## Implementation Phases

### Phase 1 — Foundation (no external dependencies)

1. Models + Alembic migration (flow_definitions, flow_instances)
2. Flow service (state machine engine: advance_flow)
3. Flow Celery tasks (advance_flow_task, poll_waiting_flows)
4. Flow API routes (CRUD for definitions + instances)

### Phase 2 — Connector Capabilities (external API integration)

5. Feishu connector: `create_approval_instance()`
6. Feishu connector: `send_message()`
7. Kingdee ERP connector: `submit()`, `audit()`, new FormIDs (SAL_RETURNSTOCK, AR_RECEIVABLE, AR_REFUNDBILL)

### Phase 3 — Step Handlers + Integration

8. All 8 step handler functions
9. CRM polling trigger (poll_crm_returns)
10. Seed default FlowDefinition for crm_return_flow

### Phase 4 — Testing

11. Unit tests for state machine logic
12. Integration test with real APIs (end-to-end)

### Estimated Effort

| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 1 | ~0.5 day | Standard CRUD + state machine, no external deps |
| Phase 2 | ~1 day | Feishu/Kingdee API integration with debugging |
| Phase 3 | ~0.5 day | Handler logic is straightforward, mainly data mapping |
| Phase 4 | ~0.5 day | Unit tests + end-to-end verification |
| **Total** | **~2.5 days** | |

## Connector Credentials Reference

- **纷享销客 CRM** (connector id=2): Return request entity TBD
- **飞书 OA** (connector id=4): approval_code = `F010288B-1D73-4424-AE8E-E5516EAF03F7`
- **金蝶 ERP** (connector id=3): FormIDs = SAL_RETURNSTOCK, AR_RECEIVABLE, AR_REFUNDBILL
