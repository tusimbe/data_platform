# 数据模型规范

## 目的

定义平台的数据存储行为，包括双层存储策略（原始层 + 统一层）、元数据表和字段映射系统。

## 需求

### 需求：原始数据存储
系统应（SHALL）以 JSONB 原始格式存储从外部系统拉取的所有数据，支持数据追溯和重新处理。

#### 场景：拉取时存储原始数据
- 假设（GIVEN）从外部连接器拉取了数据
- 当（WHEN）数据被持久化时
- 则（THEN）每条记录存储到 raw_data 表，包含 connector_id、entity、external_id 和完整的原始 JSONB 数据
- 且（AND）记录 synced_at 同步时间戳
- 且（AND）sync_log_id 关联到本次同步执行记录

#### 场景：原始数据更新插入
- 假设（GIVEN）已存在相同 (connector_id, entity, external_id) 的记录
- 当（WHEN）拉取到该记录的新版本时
- 则（THEN）更新已有 raw_data 行的 JSONB 数据
- 且（AND）更新 synced_at 时间戳

#### 场景：按来源查询原始数据
- 假设（GIVEN）指定了 connector_id 和实体类型
- 当（WHEN）查询原始数据时
- 则（THEN）返回所有匹配记录及其原始 JSONB 数据

### 需求：统一数据模型
系统应（SHALL）为核心业务领域维护标准化表，通过字段映射从原始数据转换而来。

#### 场景：统一客户记录
- 假设（GIVEN）从纷享销客CRM拉取的原始客户数据
- 当（WHEN）应用字段映射后
- 则（THEN）在 unified_customers 中创建/更新一条标准化记录，包含标准字段（名称、电话、邮箱、公司、地址等）
- 且（AND）保留 source_system 和 external_id 用于数据溯源

#### 场景：多来源实体
- 假设（GIVEN）CRM 和 ERP 中都存在客户数据
- 当（WHEN）两边都同步完成后
- 则（THEN）unified_customers 中存在两条记录，source_system 值不同
- 且（AND）可以（MAY）使用 matching_key（如公司名+电话）识别重复记录

### 需求：数据溯源
统一表中的每条记录必须（MUST）能关联回其来源系统和原始数据。

#### 场景：追溯统一记录到来源
- 假设（GIVEN）unified_orders 中的一条记录
- 当（WHEN）查询其来源时
- 则（THEN）记录包含 source_system、external_id 和 source_data_id（关联 raw_data 的外键）
- 且（AND）可通过 source_data_id 获取原始 raw_data

### 需求：字段映射配置
系统应（SHALL）支持可配置的字段映射，在外部系统字段和统一模型字段之间建立对应关系，无需修改代码。

#### 场景：定义字段映射
- 假设（GIVEN）指定了连接器类型、实体和统一表
- 当（WHEN）创建字段映射（如 "FBillNo" → "order_number"）时
- 则（THEN）映射存储到 field_mappings 表
- 且（AND）后续同步操作使用此映射进行数据转换

#### 场景：更新字段映射
- 假设（GIVEN）已有的字段映射
- 当（WHEN）修改映射后
- 则（THEN）新的同步操作使用更新后的映射
- 且（AND）之前已同步的数据不会自动重新映射（需手动重新处理）

#### 场景：复杂字段映射
- 假设（GIVEN）映射需要转换处理（如日期格式转换、值查找）
- 当（WHEN）映射包含转换表达式时
- 则（THEN）在同步过程中应用转换
- 且（AND）支持的转换包括：date_format（日期格式）、value_map（值映射）、concat（拼接）、split（分割）

### 需求：实体模式注册
系统宜（SHOULD）维护各外部系统中每个实体的字段结构元数据。

#### 场景：注册实体模式
- 假设（GIVEN）连接器的 get_schema() 返回了字段定义
- 当（WHEN）模式被存储时
- 则（THEN）entity_schemas 表包含该连接器+实体的字段名、类型和是否必填

#### 场景：模式用于校验
- 假设（GIVEN）已注册某实体的模式
- 当（WHEN）拉取数据时
- 则（THEN）拉取的数据可以（MAY）根据模式进行校验
- 且（AND）校验失败记录为警告（不阻止同步）

## 统一表定义

### 需求：统一客户表
系统应（SHALL）维护 unified_customers 表，包含标准化的客户字段。

#### 场景：客户表字段
- 假设（GIVEN）unified_customers 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、name、company、phone、email、address、industry、status、created_at、updated_at、synced_at

### 需求：统一订单表
系统应（SHALL）维护 unified_orders 表，包含标准化的订单字段。

#### 场景：订单表字段
- 假设（GIVEN）unified_orders 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、order_number、order_type（销售/采购）、customer_id、total_amount、currency、status、order_date、created_at、updated_at、synced_at

### 需求：统一产品表
系统应（SHALL）维护 unified_products 表，包含标准化的产品/物料字段。

#### 场景：产品表字段
- 假设（GIVEN）unified_products 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、name、sku、category、description、unit、status、created_at、updated_at、synced_at

### 需求：统一库存表
系统应（SHALL）维护 unified_inventory 表，包含标准化的库存字段。

#### 场景：库存表字段
- 假设（GIVEN）unified_inventory 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、product_id、warehouse、quantity、available_quantity、unit、updated_at、synced_at

### 需求：统一项目表
系统应（SHALL）维护 unified_projects 表，包含标准化的项目字段。

#### 场景：项目表字段
- 假设（GIVEN）unified_projects 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、name、description、status、priority、start_date、end_date、owner、created_at、updated_at、synced_at

### 需求：统一联系人表
系统应（SHALL）维护 unified_contacts 表，包含标准化的联系人字段。

#### 场景：联系人表字段
- 假设（GIVEN）unified_contacts 表
- 则（THEN）必须包含：id、source_system、external_id、source_data_id、name、phone、email、company、department、position、created_at、updated_at、synced_at
