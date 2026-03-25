# Data Model Specification

## Purpose

Define the data storage behavior of the platform, including the dual-layer storage strategy (raw + unified), metadata tables, and field mapping system.

## Requirements

### Requirement: Raw Data Storage
The system SHALL store all data pulled from external systems in its original format using JSONB, enabling traceability and reprocessing.

#### Scenario: Store raw data on pull
- GIVEN data pulled from an external connector
- WHEN the data is persisted
- THEN each record is stored in the raw_data table with connector_id, entity, external_id, and the full original data as JSONB
- AND the synced_at timestamp is recorded
- AND the sync_log_id links to the sync execution

#### Scenario: Upsert raw data
- GIVEN a record with the same (connector_id, entity, external_id) already exists
- WHEN a new version of the record is pulled
- THEN the existing raw_data row is updated with the new JSONB data
- AND the synced_at timestamp is updated

#### Scenario: Query raw data by source
- GIVEN a connector_id and entity type
- WHEN raw data is queried
- THEN all matching records are returned with their original JSONB data

### Requirement: Unified Data Models
The system SHALL maintain standardized tables for core business domains, derived from raw data via field mappings.

#### Scenario: Unified customer record
- GIVEN raw customer data from Fenxiangxiaoke CRM
- WHEN field mappings are applied
- THEN a unified_customers record is created/updated with standardized fields (name, phone, email, company, address, etc.)
- AND source_system and external_id are preserved for traceability

#### Scenario: Multi-source entity
- GIVEN customer data exists in both CRM and ERP
- WHEN both are synced
- THEN both records exist in unified_customers with different source_system values
- AND a matching_key (e.g., company name + phone) MAY be used to identify duplicates

### Requirement: Source Traceability
Every record in a unified table MUST link back to its source system and original data.

#### Scenario: Trace unified record to source
- GIVEN a record in unified_orders
- WHEN the source is queried
- THEN the record contains source_system, external_id, and source_data_id (FK to raw_data)
- AND the original raw data can be retrieved via source_data_id

### Requirement: Field Mapping Configuration
The system SHALL support configurable field mappings between external system fields and unified model fields, without requiring code changes.

#### Scenario: Define a field mapping
- GIVEN a connector type, entity, and unified table
- WHEN a field mapping is created (e.g., "FBillNo" → "order_number")
- THEN it is stored in the field_mappings table
- AND subsequent sync operations use this mapping for data transformation

#### Scenario: Update field mapping
- GIVEN an existing field mapping
- WHEN the mapping is modified
- THEN new sync operations use the updated mapping
- AND previously synced data is not automatically re-mapped (manual reprocess required)

#### Scenario: Complex field mapping
- GIVEN a mapping that requires transformation (e.g., date format conversion, value lookup)
- WHEN the mapping includes a transform expression
- THEN the transform is applied during sync
- AND supported transforms include: date_format, value_map, concat, split

### Requirement: Entity Schema Registry
The system SHOULD maintain metadata about the field structure of each entity in each external system.

#### Scenario: Register entity schema
- GIVEN a connector's get_schema() returns field definitions
- WHEN the schema is stored
- THEN entity_schemas table contains field names, types, and required flags for that connector+entity

#### Scenario: Schema used for validation
- GIVEN a registered schema for an entity
- WHEN data is pulled
- THEN pulled data MAY be validated against the schema
- AND validation failures are logged as warnings (do not block sync)

## Unified Table Definitions

### Requirement: Unified Customers Table
The system SHALL maintain a unified_customers table with standardized customer fields.

#### Scenario: Customer fields
- GIVEN the unified_customers table
- THEN it MUST include: id, source_system, external_id, source_data_id, name, company, phone, email, address, industry, status, created_at, updated_at, synced_at

### Requirement: Unified Orders Table
The system SHALL maintain a unified_orders table with standardized order fields.

#### Scenario: Order fields
- GIVEN the unified_orders table
- THEN it MUST include: id, source_system, external_id, source_data_id, order_number, order_type (sales/purchase), customer_id, total_amount, currency, status, order_date, created_at, updated_at, synced_at

### Requirement: Unified Products Table
The system SHALL maintain a unified_products table with standardized product/material fields.

#### Scenario: Product fields
- GIVEN the unified_products table
- THEN it MUST include: id, source_system, external_id, source_data_id, name, sku, category, description, unit, status, created_at, updated_at, synced_at

### Requirement: Unified Inventory Table
The system SHALL maintain a unified_inventory table with standardized inventory fields.

#### Scenario: Inventory fields
- GIVEN the unified_inventory table
- THEN it MUST include: id, source_system, external_id, source_data_id, product_id, warehouse, quantity, available_quantity, unit, updated_at, synced_at

### Requirement: Unified Projects Table
The system SHALL maintain a unified_projects table with standardized project fields.

#### Scenario: Project fields
- GIVEN the unified_projects table
- THEN it MUST include: id, source_system, external_id, source_data_id, name, description, status, priority, start_date, end_date, owner, created_at, updated_at, synced_at

### Requirement: Unified Contacts Table
The system SHALL maintain a unified_contacts table with standardized contact fields.

#### Scenario: Contact fields
- GIVEN the unified_contacts table
- THEN it MUST include: id, source_system, external_id, source_data_id, name, phone, email, company, department, position, created_at, updated_at, synced_at
