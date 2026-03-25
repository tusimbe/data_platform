# Enterprise Data Platform Design Spec

## Overview

Enterprise data platform (数据中台) for collecting, managing, and distributing data across business systems. The platform integrates 6 external systems via a unified connector framework, stores data in a dual-layer model (raw + unified), and provides REST APIs for querying and writing back.

## Context

### Business Systems to Integrate

| System | Type | Interface | Key Entities |
|--------|------|-----------|-------------|
| 金蝶云星空 (Kingdee ERP) | ERP | REST API (Open API) | Sales orders, purchase orders, inventory, BOM, financial vouchers |
| 金蝶PLM | PLM | REST API | Products, materials, design docs, change orders |
| 纷享销客 (Fenxiangxiaoke) | CRM | REST API (Open Platform) | Customers, contacts, opportunities, contracts, payments |
| 飞书 (Feishu/Lark) | OA | REST API (Open Platform) | Approvals, org structure, calendar, docs |
| 禅道 (Zentao) | Project Mgmt | REST API | Projects, requirements, tasks, bugs, sprints |
| 领星ERP (Lingxing) | Cross-border ERP | REST API (Open Platform) | Products, orders, inventory, logistics, settlements |

### Technical Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** PostgreSQL (with JSONB)
- **Task Queue:** Celery + Redis
- **ORM:** SQLAlchemy 2.0 + Alembic (migrations)
- **Deployment:** Docker containers on domestic public cloud

### Data Scale

- Small scale: ~10K records/day
- Scheduled sync (cron-based), not real-time streaming
- Bidirectional: collect from systems + write back to systems

## Architecture

### Four-Layer Architecture

```
┌──────────────────────────────────────────────────────┐
│  Layer 4: Management UI (Web)                         │
│  Connector config / Sync task mgmt / Data query       │
├──────────────────────────────────────────────────────┤
│  Layer 3: Data Service Layer (FastAPI)                │
│  REST API / Unified query / Write-back / Auth         │
├──────────────────────────────────────────────────────┤
│  Layer 2: Core Engine                                 │
│  Connector Registry / Schema Registry / Scheduler     │
├──────────────────────────────────────────────────────┤
│  Layer 1: Connector Layer                             │
│  KingdeeERP / KingdeePLM / FXXK / Feishu / Zentao / Lingxing │
├──────────────────────────────────────────────────────┤
│  Storage: PostgreSQL                                  │
│  Unified models / Raw data / Metadata / Sync logs     │
└──────────────────────────────────────────────────────┘
```

### Project Structure

```
data_platform/
├── openspec/                    # OpenSpec spec directory
│   ├── specs/                   # Behavior specs (source of truth)
│   │   ├── connectors/          # Connector specs
│   │   ├── data-model/          # Data model specs
│   │   ├── sync-engine/         # Sync engine specs
│   │   └── api/                 # API specs
│   ├── changes/                 # Active changes
│   └── config.yaml
├── src/
│   ├── connectors/              # Connector implementations
│   │   ├── base.py              # Abstract base class
│   │   ├── kingdee_erp.py
│   │   ├── kingdee_plm.py
│   │   ├── fenxiangxiaoke.py
│   │   ├── feishu.py
│   │   ├── zentao.py
│   │   └── lingxing.py
│   ├── models/                  # SQLAlchemy models
│   ├── services/                # Business logic
│   ├── api/                     # FastAPI routes
│   ├── tasks/                   # Celery async tasks
│   ├── core/                    # Config, auth, utils
│   └── main.py
├── tests/
├── alembic/                     # DB migrations
├── pyproject.toml
└── docker-compose.yml
```

## Component Design

### 1. Connector Framework

#### Abstract Base Class

Every connector implements a unified interface:

```python
class BaseConnector(ABC):
    # Lifecycle
    connect() -> None
    disconnect() -> None
    health_check() -> HealthStatus

    # Read (external system → platform)
    list_entities() -> list[EntityInfo]
    pull(entity: str, since: datetime | None, filters: dict) -> list[dict]

    # Write (platform → external system)
    push(entity: str, records: list[dict]) -> PushResult

    # Metadata
    get_schema(entity: str) -> EntitySchema
```

#### Connector Registry

- Connectors register themselves via a registry pattern
- Configuration stored in `connectors` table (type, auth credentials, enabled status)
- Auth credentials encrypted at rest

### 2. Data Model — Dual-Layer Storage

#### Layer 1: Raw Data

```sql
raw_data (
    id              BIGSERIAL PRIMARY KEY,
    connector_id    INTEGER REFERENCES connectors(id),
    entity          VARCHAR(100),      -- e.g., "sales_order"
    external_id     VARCHAR(255),      -- ID in source system
    data            JSONB,             -- Original data as-is
    synced_at       TIMESTAMPTZ,
    sync_log_id     BIGINT REFERENCES sync_logs(id),
    UNIQUE(connector_id, entity, external_id)
)
```

Stores original data from each system in JSONB format, no schema constraints. Enables traceability and reprocessing.

#### Layer 2: Unified Models

Standardized tables per business domain:

- `unified_customers` — Customers (from CRM, ERP)
- `unified_orders` — Orders (from ERP, Lingxing)
- `unified_products` — Products/materials (from ERP, PLM, Lingxing)
- `unified_inventory` — Inventory (from ERP, Lingxing)
- `unified_projects` — Projects (from Zentao)
- `unified_contacts` — Contacts (from CRM, Feishu)

Each unified table includes:
- `source_system` — Which connector provided this record
- `external_id` — ID in source system
- `source_data_id` — FK to raw_data for traceability
- `created_at`, `updated_at` — Timestamps
- Standard business fields for the domain

#### Platform Metadata Tables

| Table | Purpose |
|-------|---------|
| `connectors` | Connector configurations (type, auth, enabled) |
| `sync_tasks` | Sync task definitions (connector, entity, cron, direction) |
| `sync_logs` | Sync execution logs (start/end time, status, counts, errors) |
| `entity_schemas` | Entity field structure metadata per system |
| `field_mappings` | External field ↔ unified field mapping rules |

### 3. Sync Engine

#### Pull (Inbound) Flow

```
Celery Beat (cron trigger)
    │
    ▼
1. Pull Phase: connector.pull(entity, since=last_sync_time)
    │
    ▼
2. Transform Phase: apply field_mappings, clean data, normalize formats
    │
    ▼
3. Store Phase: upsert raw_data + upsert unified_* tables + write sync_log
```

#### Push (Outbound) Flow

```
API call or scheduled trigger
    │
    ▼
1. Read Phase: query pending write-back records from PG
    │
    ▼
2. Transform Phase: reverse field mapping, adapt to target format
    │
    ▼
3. Push Phase: connector.push(entity, records) + write sync_log
```

#### Sync Log

Every sync execution records:
- Start/end time
- Direction (pull/push)
- Entity and connector
- Total records, success count, failure count
- Error details (for failed records)

### 4. API Design

```
# Unified data query
GET  /api/v1/data/{entity}              # Query unified model
GET  /api/v1/data/{entity}/{id}         # Single record
GET  /api/v1/raw/{connector}/{entity}   # Query raw data

# Data write-back
POST /api/v1/push/{connector}/{entity}  # Push data to target system

# Connector management
GET  /api/v1/connectors                 # List connectors
POST /api/v1/connectors                 # Add connector config
PUT  /api/v1/connectors/{id}            # Update config

# Sync task management
GET  /api/v1/sync-tasks                 # List sync tasks
POST /api/v1/sync-tasks/{id}/trigger    # Manually trigger sync
GET  /api/v1/sync-logs                  # View sync logs

# Health
GET  /api/v1/health                     # Platform health check
```

## Sub-Project Decomposition

The implementation is decomposed into 7 sub-projects, each following its own OpenSpec spec → plan → implement cycle:

| # | Sub-Project | Content | Priority |
|---|-------------|---------|----------|
| 1 | Foundation Platform | Project scaffold, DB, config, auth | P0 |
| 2 | Connector Framework + First Connector | Base connector class + Kingdee ERP connector | P0 |
| 3 | Data Model & Storage | Unified data model, raw data layer, metadata tables | P0 |
| 4 | Remaining Connectors | PLM, CRM, Feishu, Zentao, Lingxing connectors | P1 |
| 5 | Data Service Layer | Unified query API, write-back API | P1 |
| 6 | Scheduling & Monitoring | Celery Beat scheduling, sync status monitoring, logging & alerts | P1 |
| 7 | Management UI | Web admin interface, connector config UI, sync task dashboard | P2 |

## Success Criteria

1. All 6 connectors can successfully pull data from their respective systems
2. Data is stored in both raw (JSONB) and unified (structured) layers
3. Field mappings are configurable without code changes
4. Write-back works for at least Kingdee ERP and CRM
5. Sync tasks run on schedule with proper logging and error handling
6. REST API provides unified query across all integrated data
7. OpenSpec specs are maintained as source of truth for all behavior

## Non-Goals (for initial version)

- Real-time streaming / CDC (Change Data Capture)
- Complex data analytics / BI dashboards
- Machine learning or AI-driven data processing
- Multi-tenant support
- Custom color themes or advanced UI customization
