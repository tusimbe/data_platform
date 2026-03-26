# P2 管理后台 MVP 设计文档

## 1. 概述

### 1.1 目标

为数据中台构建 Web 管理后台，提供连接器配置、同步任务管理、同步日志查看和系统健康监控功能。复用 P1 已实现的全部 REST API，前端为纯展示/操作层。

### 1.2 范围

**包含（MVP）：**
- Dashboard 健康看板（系统状态 + 统计摘要 + 最近日志）
- 连接器管理（CRUD + 列表分页）
- 同步任务管理（CRUD + 手动触发 + 列表分页）
- 同步日志查看（列表 + 筛选 + 详情展开）
- API Key 认证（登录页 + localStorage 持久化）

**不包含（延后）：**
- 数据查询页面（`GET /api/v1/data/*` 的前端界面）
- Celery 任务监控 / Flower 集成
- 多语言 i18n
- 暗色主题 / 自定义主题
- 用户名密码认证 / JWT / RBAC

### 1.3 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18+ | UI 框架 |
| TypeScript | 5+ | 类型安全 |
| Ant Design | 5+ | UI 组件库 |
| Vite | 5+ | 构建工具 |
| axios | 1+ | HTTP 客户端 |
| React Router | 6+ | 前端路由 |

### 1.4 部署方式

前端打包为静态文件（`frontend/dist/`），由 FastAPI 的 `StaticFiles` 中间件直接服务。不引入 Nginx 或独立前端服务器。

生产构建流程：
```
cd frontend && npm run build   # 输出到 frontend/dist/
```

FastAPI 挂载：
```python
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

## 2. 架构

### 2.1 整体架构

```
┌────────────────────────────────────────────┐
│  浏览器                                      │
│  React + Ant Design SPA                     │
│  ├── /login          API Key 登录           │
│  ├── /dashboard      健康看板               │
│  ├── /connectors     连接器管理             │
│  ├── /sync-tasks     同步任务管理           │
│  └── /sync-logs      同步日志               │
└────────────────┬───────────────────────────┘
                 │ HTTP (axios)
                 │ X-API-Key header
                 ▼
┌────────────────────────────────────────────┐
│  FastAPI 后端                                │
│  /api/v1/*         已有 REST API            │
│  /                 StaticFiles (SPA)        │
└────────────────────────────────────────────┘
```

### 2.2 前端项目结构

```
frontend/
├── package.json
├── vite.config.ts           # dev proxy /api → FastAPI
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx             # React 入口
    ├── App.tsx              # 路由定义 + AuthGuard
    ├── api/
    │   └── client.ts        # axios 实例 + 拦截器
    ├── pages/
    │   ├── Login.tsx         # API Key 登录页
    │   ├── Dashboard.tsx     # 健康看板
    │   ├── Connectors.tsx    # 连接器管理
    │   ├── SyncTasks.tsx     # 同步任务管理
    │   └── SyncLogs.tsx      # 同步日志
    ├── components/
    │   ├── AppLayout.tsx     # 侧边栏 + 顶栏布局
    │   └── HealthStatus.tsx  # 健康状态徽标组件
    └── utils/
        └── auth.ts          # API Key 存取 + 认证状态
```

### 2.3 后端改动

仅修改 `src/main.py`：

1. **StaticFiles 挂载**：将 `frontend/dist/` 目录挂载到根路径
2. **SPA Fallback**：添加 catch-all 路由，对非 `/api` 前缀的 GET 请求返回 `index.html`
3. **挂载顺序**：API 路由优先注册，StaticFiles 最后挂载

```python
# src/main.py 改动示意
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ... 现有 API 路由注册 ...

# SPA fallback — 必须在 API 路由之后
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dir):
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))
```

## 3. 页面设计

### 3.1 登录页 (`/login`)

**功能：**
- 单个输入框：API Key
- 登录按钮
- 输入后调用 `GET /api/v1/connectors?page=1&page_size=1`（携带 Key）验证有效性（注意：`/health` 无需认证，不能用来验证 Key）
- 成功：Key 存入 `localStorage`，跳转 `/dashboard`
- 失败：显示错误提示（"API Key 无效"）

**布局：**
- 居中卡片，应用名称 + 版本号 + 输入框 + 按钮
- 使用 Ant Design `Card` + `Input.Password` + `Button`

**认证守卫：**
- 所有非 `/login` 路由包裹 `AuthGuard` 组件
- `AuthGuard` 检查 `localStorage` 中是否有 API Key
- 无 Key 则重定向到 `/login`
- API 返回 401 时清除 Key 并跳转 `/login`

### 3.2 Dashboard (`/dashboard`)

**功能：**
- 系统健康状态：调用 `GET /api/v1/health`
  - 显示 overall status（healthy/degraded/unhealthy）及颜色指示
  - 三个组件卡片：Database、Redis、Celery，各显示状态 + 延迟（healthy 时显示 `latency_ms`，unhealthy 时显示 `error` 信息；Celery healthy 时额外显示 `workers` 数量）
- 统计摘要卡片：
  - 连接器总数 / 启用数：调用 `GET /api/v1/connectors`
  - 同步任务总数 / 启用数：调用 `GET /api/v1/sync-tasks`
- 最近同步日志：调用 `GET /api/v1/sync-logs?page_size=10`
  - 表格展示：时间、entity、状态、记录数

**布局：**
- 顶部：健康状态卡片行（3 列）
- 中部：统计摘要卡片行（2 列）
- 底部：最近同步日志表格

**刷新：**
- 页面加载时获取数据
- 提供手动刷新按钮
- 不实现自动轮询（MVP 不需要）

### 3.3 连接器管理 (`/connectors`)

**列表页功能：**
- 表格列：ID、名称、类型、base_url、启用状态、创建时间、操作
- 分页：使用 Ant Design `Table` 内置分页，调用 `GET /api/v1/connectors?page=N&page_size=M`
- 操作列：编辑按钮、禁用/启用按钮（`PUT /api/v1/connectors/{id}` 设置 `enabled`）、删除按钮

**创建/编辑：**
- 使用 Ant Design `Modal`（模态框）
- 表单字段：
  - 名称（`Input`，必填）
  - 描述（`Input.TextArea`，可选）
  - 类型（`Select` 下拉，选项：`kingdee_erp`, `kingdee_plm`, `feishu`, `fenxiangxiaoke`, `lingxing`, `zentao`）
  - Base URL（`Input`，必填）
  - Auth Config（`Input.TextArea`，JSON 格式，必填）
  - 启用（`Switch`，默认开启）
- 创建：`POST /api/v1/connectors`
- 编辑：`PUT /api/v1/connectors/{id}`

**删除：**
- `Popconfirm` 确认对话框
- 调用 `DELETE /api/v1/connectors/{id}`
- 成功后刷新列表

### 3.4 同步任务管理 (`/sync-tasks`)

**列表页功能：**
- 表格列：ID、连接器 ID、Entity、Direction、Cron、启用状态、上次同步、下次同步、操作
- 分页：调用 `GET /api/v1/sync-tasks?page=N&page_size=M`
- 操作列：编辑、触发、删除

**创建/编辑：**
- 使用 Ant Design `Modal`
- 表单字段：
  - 连接器（`Select`，从 `GET /api/v1/connectors` 加载选项）
  - Entity（`Input`，必填）
  - Direction（`Select`：pull / push）
  - Cron Expression（`Input`，可选）
  - 启用（`Switch`，默认开启）
- 创建：`POST /api/v1/sync-tasks`
- 编辑：`PUT /api/v1/sync-tasks/{id}`

**手动触发：**
- 点击"触发"按钮
- 调用 `POST /api/v1/sync-tasks/{id}/trigger`
- 成功（202）：`message.success("同步任务已加入队列")`
- 失败（400/404）：`message.error(detail)`

**删除：**
- `Popconfirm` 确认
- 调用 `DELETE /api/v1/sync-tasks/{id}`

### 3.5 同步日志 (`/sync-logs`)

**列表页功能：**
- 表格列：ID、任务 ID、连接器 ID、Entity、Direction、状态、总记录数、成功数、失败数、开始时间、结束时间
- 分页：调用 `GET /api/v1/sync-logs?page=N&page_size=M`
- 筛选栏：
  - 连接器 ID（`Select`）
  - Entity（`Input`）
  - 状态（`Select`：success / failed / running）
  - 时间范围（`DatePicker.RangePicker`）
- 筛选参数拼接到 API query string

**详情展开：**
- 使用 Ant Design `Table` 的 `expandable` 属性
- 展开行显示 `error_details` JSON（使用 `<pre>` 格式化）

## 4. API Client 封装

### 4.1 axios 实例 (`api/client.ts`)

```typescript
// 概念代码，非最终实现
import axios from 'axios';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

// 请求拦截器：注入 API Key
client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('api_key');
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

// 响应拦截器：401 处理
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('api_key');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
```

### 4.2 API 调用约定

所有 API 调用通过 `client` 实例发起，返回 Promise。页面组件使用 React state + useEffect 管理数据获取。

不引入额外状态管理库（如 Redux、Zustand）。每个页面组件自管理状态，通过 axios 直接调用 API。

## 5. 布局组件

### 5.1 AppLayout

使用 Ant Design `Layout` 组件：
- `Layout.Sider`：侧边栏菜单
  - Dashboard（首页）
  - 连接器管理
  - 同步任务
  - 同步日志
- `Layout.Header`：应用名称 + 登出按钮
- `Layout.Content`：页面内容区域（`<Outlet />`）

侧边栏使用 Ant Design `Menu` 组件，通过 `React Router` 的 `useLocation` 高亮当前页面。

## 6. Vite 开发配置

### 6.1 开发代理

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

开发时前端运行在 `localhost:5173`，API 请求代理到 FastAPI `localhost:8000`。

### 6.2 构建输出

```typescript
export default defineConfig({
  build: {
    outDir: 'dist',
  },
});
```

## 7. 错误处理

### 7.1 全局错误

- axios 响应拦截器处理 401（跳转登录）
- 网络错误：`message.error("网络连接失败")`

### 7.2 表单错误

- 后端 400 错误：显示 `detail` 字段内容
- 后端 422 验证错误：显示字段级别错误
- 后端 404：显示 "资源不存在"

### 7.3 加载状态

- 所有数据获取使用 Ant Design `Table` 的 `loading` 属性
- 表单提交使用 `Button` 的 `loading` 属性
- Dashboard 统计卡片使用 `Skeleton` 占位

## 8. 已知约束

1. **API Key 明文存储**：localStorage 中的 API Key 未加密。MVP 阶段可接受，后续可引入 JWT。
2. **无实时更新**：Dashboard 不自动刷新，需手动点击刷新按钮。
3. **无前端测试**：MVP 不包含 React 组件测试或 E2E 测试。
4. **单一 API Key**：所有管理员共享同一个 Key，无角色区分。
5. **Auth Config 原始 JSON**：连接器的 `auth_config` 字段直接编辑 JSON 文本，不提供结构化表单。

## 9. 子项目拆分

P2 MVP 作为单一子项目实施，按以下任务顺序：

1. 前端项目脚手架（Vite + React + Ant Design + TypeScript 初始化）
2. API Client 封装 + 认证工具
3. 布局组件 + 路由 + 登录页
4. Dashboard 页面
5. 连接器管理页面
6. 同步任务管理页面
7. 同步日志页面
8. 后端 StaticFiles 挂载 + SPA fallback
9. Docker Compose 更新（前端构建步骤）
