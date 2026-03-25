# 同步引擎规范

## 目的

定义数据同步引擎的行为规范。同步引擎负责编排从外部系统拉取数据、转换数据、存储数据，以及按计划将数据推送回外部系统的全过程。

## 需求

### 需求：同步任务配置
系统应（SHALL）允许定义同步任务，指定使用哪个连接器、实体、方向和调度计划。

#### 场景：创建拉取同步任务
- 假设（GIVEN）一个 connector_id、实体类型和 cron 表达式
- 当（WHEN）创建方向为 direction="pull" 的同步任务时
- 则（THEN）任务持久化到 sync_tasks 表
- 且（AND）Celery Beat 将其注册为定时执行任务

#### 场景：创建推送同步任务
- 假设（GIVEN）一个 connector_id、实体类型和 cron 表达式
- 当（WHEN）创建方向为 direction="push" 的同步任务时
- 则（THEN）任务持久化到 sync_tasks 表
- 且（AND）该任务将把待处理记录从中台推送到外部系统

#### 场景：禁用同步任务
- 假设（GIVEN）一个活跃的同步任务
- 当（WHEN）禁用该任务时
- 则（THEN）Celery Beat 停止对其调度
- 且（AND）其状态在数据库中设为 "disabled"

### 需求：定时执行
系统应（SHALL）使用 Celery Beat 配合 cron 表达式定时执行同步任务。

#### 场景：cron 触发拉取
- 假设（GIVEN）一个同步任务配置为 cron="0 */2 * * *"（每 2 小时）
- 当（WHEN）cron 触发时
- 则（THEN）同步任务作为 Celery 任务入队
- 且（AND）对配置的连接器和实体执行拉取流程

#### 场景：手动触发
- 假设（GIVEN）一个已有的同步任务
- 当（WHEN）通过 API 请求手动触发时
- 则（THEN）同步任务立即入队
- 且（AND）无论 cron 调度如何，立即执行

### 需求：拉取同步流程
系统应（SHALL）实现三阶段拉取同步：获取、转换、存储。

#### 场景：拉取同步成功
- 假设（GIVEN）一个拉取同步任务，connector=kingdee_erp，entity=sales_order
- 当（WHEN）同步执行时
- 则（THEN）阶段1：connector.pull() 从外部系统获取记录
- 且（AND）阶段2：应用字段映射转换数据
- 且（AND）阶段3：更新插入 raw_data + 更新插入统一表
- 且（AND）创建 sync_log 记录，status="success"，包含记录条数和耗时

#### 场景：增量拉取同步
- 假设（GIVEN）同步任务之前已执行过
- 当（WHEN）再次执行时
- 则（THEN）调用 connector.pull(since=上次成功同步时间)
- 且（AND）仅处理上次同步后新增/修改的记录

#### 场景：拉取同步部分失败
- 假设（GIVEN）一批拉取的记录中部分转换失败
- 当（WHEN）同步处理记录时
- 则（THEN）转换成功的记录正常存储
- 且（AND）失败记录的详情写入 sync_log
- 且（AND）同步以 status="partial_success" 完成

### 需求：推送同步流程
系统应（SHALL）实现三阶段推送同步：读取、转换、推送。

#### 场景：推送同步成功
- 假设（GIVEN）一个推送同步任务，connector=fenxiangxiaoke，entity=customer
- 当（WHEN）同步执行时
- 则（THEN）阶段1：从数据库读取待回写记录
- 且（AND）阶段2：反向字段映射，适配目标系统格式
- 且（AND）阶段3：connector.push() 发送记录到外部系统
- 且（AND）创建 sync_log 记录，包含状态和条数

#### 场景：使用回写队列推送
- 假设（GIVEN）pending_writes 表中有标记待回写的记录
- 当（WHEN）推送同步执行时
- 则（THEN）拾取标记的记录，推送后标记为已完成
- 且（AND）失败的记录保持待处理状态，等待重试

### 需求：同步日志
系统必须（MUST）对每次同步执行记录详细日志。

#### 场景：同步日志内容
- 假设（GIVEN）一次已完成的同步执行
- 则（THEN）sync_log 记录包含：
  - sync_task_id（同步任务ID）
  - connector_id（连接器ID）
  - entity（实体类型）
  - direction（方向：pull/push）
  - started_at（开始时间）、finished_at（结束时间）
  - total_records（总记录数）、success_count（成功数）、failure_count（失败数）
  - status（状态：success/partial_success/failure）
  - error_details（JSONB 格式，记录失败详情）

#### 场景：查询同步历史
- 假设（GIVEN）指定了 connector_id 或 sync_task_id
- 当（WHEN）查询同步日志时
- 则（THEN）返回所有匹配日志，按 started_at 倒序排列
- 且（AND）支持按状态和日期范围过滤

### 需求：错误处理与恢复
系统必须（MUST）优雅地处理同步失败并支持恢复。

#### 场景：连接器不可用
- 假设（GIVEN）连接器对应的外部系统宕机
- 当（WHEN）同步任务尝试执行时
- 则（THEN）同步失败，并给出清晰的错误信息
- 且（AND）创建 sync_log，status="failure"，包含错误信息
- 且（AND）下次定时执行时自动重试

#### 场景：数据库写入失败
- 假设（GIVEN）同步成功拉取了数据，但存储阶段失败
- 当（WHEN）数据库错误发生时
- 则（THEN）事务回滚
- 且（AND）不提交部分数据
- 且（AND）sync_log 记录失败信息和错误详情

### 需求：并发控制
系统必须（MUST）防止同一同步任务的重复并发执行。

#### 场景：防止重复执行
- 假设（GIVEN）一个同步任务正在运行中
- 当（WHEN）同一任务再次被触发（定时或手动）时
- 则（THEN）第二次执行被跳过
- 且（AND）记录一条警告日志
