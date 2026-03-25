# 连接器规范

## 目的

定义连接器框架的行为规范。连接器框架负责将外部业务系统与数据中台集成。每个连接器封装一个外部系统的 API 交互细节，并暴露统一接口用于数据拉取（入站）和推送（出站）。

## 需求

### 需求：统一连接器接口
系统应（SHALL）提供一个抽象基类，所有连接器必须（MUST）实现该基类，确保不同外部系统的接口一致性。

#### 场景：连接器实现必需方法
- 假设（GIVEN）一个新的连接器类用于某个外部系统
- 当（WHEN）连接器被实例化时
- 则（THEN）它必须实现：connect()、disconnect()、health_check()、list_entities()、pull()、push()、get_schema()
- 且（AND）如果未实现任何必需方法，则在导入时抛出 TypeError

### 需求：连接器注册
系统应（SHALL）维护一个所有可用连接器的注册表，支持按连接器类型动态查找。

#### 场景：注册连接器
- 假设（GIVEN）一个使用 @register_connector("kingdee_erp") 装饰的连接器类
- 当（WHEN）应用启动时
- 则（THEN）该连接器以键名 "kingdee_erp" 在注册表中可用

#### 场景：查找连接器
- 假设（GIVEN）一个连接器类型字符串 "fenxiangxiaoke"
- 当（WHEN）查询注册表时
- 则（THEN）返回对应的连接器类
- 且（AND）如果类型未知，则抛出 ConnectorNotFoundError

### 需求：连接器配置
系统应（SHALL）将连接器配置存储在数据库中，包括连接参数和认证凭据。

#### 场景：创建连接器配置
- 假设（GIVEN）有效的连接器参数（类型、名称、认证凭据、基础 URL）
- 当（WHEN）保存连接器配置时
- 则（THEN）配置持久化到 connectors 表
- 且（AND）认证凭据静态加密存储

#### 场景：更新连接器配置
- 假设（GIVEN）一个已有的连接器配置
- 当（WHEN）更新认证凭据时
- 则（THEN）旧凭据被新的加密凭据替换
- 且（AND）下次同步时连接器可用新凭据进行认证

### 需求：健康检查
系统必须（MUST）支持对每个已配置连接器的健康检查，以验证连通性。

#### 场景：连接器健康
- 假设（GIVEN）一个正确配置的连接器
- 当（WHEN）调用 health_check() 时
- 则（THEN）返回 HealthStatus，status="healthy"，并包含延迟毫秒数

#### 场景：连接器不健康
- 假设（GIVEN）一个认证凭据无效的连接器
- 当（WHEN）调用 health_check() 时
- 则（THEN）返回 HealthStatus，status="unhealthy"，并包含错误信息
- 且（AND）错误被记录到日志

### 需求：数据拉取（入站）
系统应（SHALL）支持从外部系统拉取数据，支持全量和增量两种模式。

#### 场景：全量拉取
- 假设（GIVEN）一个连接器和一个实体类型（如 "sales_order"）
- 当（WHEN）调用 pull(entity="sales_order", since=None) 时
- 则（THEN）返回该实体的所有记录，格式为字典列表

#### 场景：增量拉取
- 假设（GIVEN）一个连接器、一个实体类型和上次同步时间戳
- 当（WHEN）调用 pull(entity="sales_order", since=last_sync_time) 时
- 则（THEN）仅返回 last_sync_time 之后创建或修改的记录

#### 场景：带过滤条件的拉取
- 假设（GIVEN）附加的过滤参数
- 当（WHEN）调用 pull(entity="sales_order", filters={"status": "approved"}) 时
- 则（THEN）仅返回匹配过滤条件的记录

#### 场景：拉取失败
- 假设（GIVEN）连接器在拉取过程中遇到 API 错误
- 当（WHEN）错误发生时
- 则（THEN）抛出 ConnectorPullError，包含原始错误详情
- 且（AND）错误被记录日志，包含 connector_id、entity 和时间戳

### 需求：数据推送（出站）
系统应（SHALL）支持将数据从中台推送回外部系统。

#### 场景：推送成功
- 假设（GIVEN）一批需要推送到外部系统的记录
- 当（WHEN）调用 push(entity="customer", records=[...]) 时
- 则（THEN）每条记录在外部系统中被创建或更新
- 且（AND）返回 PushResult，包含 success_count 和 failure_count

#### 场景：部分推送失败
- 假设（GIVEN）一批记录中部分在外部系统验证失败
- 当（WHEN）调用 push() 时
- 则（THEN）成功推送的记录被提交
- 且（AND）失败的记录在 PushResult.failures 中报告，包含错误详情
- 且（AND）同步继续执行（不因单条记录失败而中止）

### 需求：实体模式发现
系统宜（SHOULD）支持从外部系统发现实体的字段结构。

#### 场景：获取实体模式
- 假设（GIVEN）一个连接器和一个实体类型
- 当（WHEN）调用 get_schema(entity="customer") 时
- 则（THEN）返回 EntitySchema，包含字段名、类型和是否必填

### 需求：限流与重试
系统必须（MUST）遵守外部 API 的速率限制，并实现带退避的重试机制。

#### 场景：触发限流
- 假设（GIVEN）外部 API 返回 429（请求过多）响应
- 当（WHEN）连接器遇到该响应时
- 则（THEN）等待 Retry-After 头指定的时间（或默认退避时间）
- 且（AND）最多重试 3 次

#### 场景：瞬时错误重试
- 假设（GIVEN）遇到瞬时网络错误（超时、502、503）
- 当（WHEN）连接器遇到该错误时
- 则（THEN）以指数退避重试（1秒、2秒、4秒）
- 且（AND）3 次失败后抛出 ConnectorError

## 各系统连接器

### 需求：金蝶ERP连接器
系统应（SHALL）提供金蝶云星空的连接器，通过其 Open API 接入。

#### 场景：金蝶认证
- 假设（GIVEN）有效的金蝶 API 凭据（app_id、app_secret、acct_id）
- 当（WHEN）调用 connect() 时
- 则（THEN）获取会话令牌并缓存，用于后续请求

#### 场景：从金蝶拉取销售订单
- 假设（GIVEN）一个已配置的金蝶ERP连接器
- 当（WHEN）调用 pull(entity="sales_order") 时
- 则（THEN）通过金蝶 Open API 获取销售订单数据
- 且（AND）以连接器标准字典格式返回

### 需求：金蝶PLM连接器
系统应（SHALL）提供金蝶PLM的连接器，通过其 API 接入。

### 需求：纷享销客CRM连接器
系统应（SHALL）提供纷享销客CRM的连接器，通过其开放平台 API 接入。

### 需求：飞书连接器
系统应（SHALL）提供飞书的连接器，通过其开放平台 API 接入。

### 需求：禅道连接器
系统应（SHALL）提供禅道的连接器，通过其 REST API 接入。

### 需求：领星ERP连接器
系统应（SHALL）提供领星ERP的连接器，通过其开放平台 API 接入。
