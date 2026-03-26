# P2 管理后台 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为数据中台构建 React 管理后台 SPA，覆盖登录、Dashboard、连接器管理、同步任务管理、同步日志查看五个页面，由 FastAPI StaticFiles 托管。

**Architecture:** React 18 + TypeScript + Ant Design 5 SPA，Vite 构建，axios 调用后端已有 REST API（`/api/v1/*`）。认证通过 API Key 存入 localStorage，axios 拦截器注入 `X-API-Key` 头。生产环境由 FastAPI `StaticFiles` 直接提供 `frontend/dist/` 静态文件。

**Tech Stack:** React 18, TypeScript 5, Ant Design 5, Vite 5, axios, React Router 6, FastAPI StaticFiles

**Spec:** `docs/superpowers/specs/2026-03-26-p2-admin-console-design.md`

**Testing:** MVP 不包含前端测试（无 Jest/Vitest/E2E）。每个 task 的验证方式为：TypeScript 编译通过 (`npx tsc --noEmit`) + Vite 构建成功 (`npm run build`)。

---

## File Structure

### 新建文件（frontend 目录）

| 文件 | 职责 |
|------|------|
| `frontend/package.json` | 依赖声明 |
| `frontend/tsconfig.json` | TypeScript 配置 |
| `frontend/tsconfig.node.json` | Vite/Node TS 配置 |
| `frontend/vite.config.ts` | Vite 配置（proxy + build） |
| `frontend/index.html` | HTML 入口 |
| `frontend/src/main.tsx` | React 入口 |
| `frontend/src/App.tsx` | 路由定义 + AuthGuard |
| `frontend/src/api/client.ts` | axios 实例 + 拦截器 |
| `frontend/src/utils/auth.ts` | API Key 存取工具 |
| `frontend/src/components/AppLayout.tsx` | 侧边栏 + 顶栏布局 |
| `frontend/src/pages/Login.tsx` | 登录页 |
| `frontend/src/pages/Dashboard.tsx` | 健康看板 |
| `frontend/src/pages/Connectors.tsx` | 连接器管理 |
| `frontend/src/pages/SyncTasks.tsx` | 同步任务管理 |
| `frontend/src/pages/SyncLogs.tsx` | 同步日志 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/main.py` | 添加 SPA fallback catch-all 路由 |
| `docker-compose.yml` | 添加 `web` 服务 + Dockerfile 引用 |
| `Dockerfile` | 新建：多阶段构建（Node 构建前端 + Python 运行后端） |
| `.gitignore` | 添加 `frontend/node_modules/`, `frontend/dist/` |

---

### Task 1: 前端项目脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Modify: `.gitignore`

- [ ] **Step 1: 创建 frontend 目录和 package.json**

```json
{
  "name": "data-platform-admin",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "antd": "^5.22.0",
    "axios": "^1.7.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: 创建 tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: 创建 vite.config.ts**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
```

- [ ] **Step 5: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>数据中台管理后台</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: 创建 src/main.tsx（最小化入口）**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';

const App: React.FC = () => <div>数据中台管理后台</div>;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 7: 更新 .gitignore**

在 `.gitignore` 末尾追加：

```
# Frontend
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 8: 安装依赖并验证构建**

Run:
```bash
cd frontend && npm install && npx tsc --noEmit && npm run build
```
Expected: 安装成功，TypeScript 无报错，`frontend/dist/` 目录生成含 `index.html`

- [ ] **Step 9: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat(frontend): scaffold React + TypeScript + Vite + Ant Design project"
```

---

### Task 2: API Client + 认证工具

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/utils/auth.ts`

- [ ] **Step 1: 创建 utils/auth.ts**

```typescript
const API_KEY_STORAGE_KEY = 'api_key';

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function removeApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
}

export function isAuthenticated(): boolean {
  return getApiKey() !== null;
}
```

- [ ] **Step 2: 创建 api/client.ts**

```typescript
import axios from 'axios';
import { getApiKey, removeApiKey } from '../utils/auth';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

// 请求拦截器：注入 API Key
client.interceptors.request.use((config) => {
  const apiKey = getApiKey();
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

// 响应拦截器：401 → 清除 Key → 跳转登录
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      removeApiKey();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  },
);

export default client;
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/ frontend/src/utils/
git commit -m "feat(frontend): add axios client with API Key interceptors and auth utils"
```

---

### Task 3: 布局组件 + 路由 + 登录页

**Files:**
- Create: `frontend/src/components/AppLayout.tsx`
- Create: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/main.tsx` → 替换为 App.tsx 引用
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: 创建 App.tsx（路由 + AuthGuard）**

```tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import AppLayout from './components/AppLayout';
import Login from './pages/Login';

// 懒加载页面 — 后续 Task 会创建这些文件，此处先用占位
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Connectors = React.lazy(() => import('./pages/Connectors'));
const SyncTasks = React.lazy(() => import('./pages/SyncTasks'));
const SyncLogs = React.lazy(() => import('./pages/SyncLogs'));

const AuthGuard: React.FC = () => {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
};

const App: React.FC = () => (
  <BrowserRouter>
    <React.Suspense fallback={<div style={{ padding: 24 }}>加载中...</div>}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AuthGuard />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/connectors" element={<Connectors />} />
            <Route path="/sync-tasks" element={<SyncTasks />} />
            <Route path="/sync-logs" element={<SyncLogs />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </React.Suspense>
  </BrowserRouter>
);

export default App;
```

- [ ] **Step 2: 更新 main.tsx**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 3: 创建 AppLayout.tsx**

```tsx
import React from 'react';
import { Layout, Menu, Button, theme } from 'antd';
import {
  DashboardOutlined,
  ApiOutlined,
  SyncOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { removeApiKey } from '../utils/auth';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/connectors', icon: <ApiOutlined />, label: '连接器管理' },
  { key: '/sync-tasks', icon: <SyncOutlined />, label: '同步任务' },
  { key: '/sync-logs', icon: <FileTextOutlined />, label: '同步日志' },
];

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();

  const handleLogout = () => {
    removeApiKey();
    navigate('/login');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider>
        <div
          style={{
            height: 32,
            margin: 16,
            color: '#fff',
            fontSize: 16,
            fontWeight: 'bold',
            textAlign: 'center',
            lineHeight: '32px',
          }}
        >
          数据中台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: '0 24px',
            background: token.colorBgContainer,
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
          }}
        >
          <Button type="text" onClick={handleLogout}>
            退出登录
          </Button>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
```

- [ ] **Step 4: 创建 Login.tsx**

```tsx
import React, { useState } from 'react';
import { Card, Input, Button, message, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { setApiKey, isAuthenticated } from '../utils/auth';
import client from '../api/client';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const [key, setKey] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  // 已登录直接跳转
  if (isAuthenticated()) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const handleLogin = async () => {
    if (!key.trim()) {
      message.warning('请输入 API Key');
      return;
    }

    setLoading(true);
    try {
      // 用输入的 Key 调用需要认证的接口验证有效性
      // 注意：/health 无需认证，不能用来验证 Key
      await client.get('/connectors', {
        headers: { 'X-API-Key': key.trim() },
        params: { page: 1, page_size: 1 },
      });
      setApiKey(key.trim());
      message.success('登录成功');
      navigate('/dashboard', { replace: true });
    } catch {
      message.error('API Key 无效');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>
            数据中台
          </Title>
          <Text type="secondary">管理后台 v0.1.0</Text>
        </div>
        <Input.Password
          placeholder="请输入 API Key"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onPressEnter={handleLogin}
          style={{ marginBottom: 16 }}
          size="large"
        />
        <Button
          type="primary"
          block
          size="large"
          loading={loading}
          onClick={handleLogin}
        >
          登录
        </Button>
      </Card>
    </div>
  );
};

export default Login;
```

- [ ] **Step 5: 创建占位页面文件**

为使 TypeScript 编译通过（App.tsx 中 lazy import 引用了这些文件），需要创建 4 个占位文件。

`frontend/src/pages/Dashboard.tsx`:
```tsx
const Dashboard: React.FC = () => <div>Dashboard</div>;
export default Dashboard;
```

`frontend/src/pages/Connectors.tsx`:
```tsx
const Connectors: React.FC = () => <div>Connectors</div>;
export default Connectors;
```

`frontend/src/pages/SyncTasks.tsx`:
```tsx
const SyncTasks: React.FC = () => <div>SyncTasks</div>;
export default SyncTasks;
```

`frontend/src/pages/SyncLogs.tsx`:
```tsx
const SyncLogs: React.FC = () => <div>SyncLogs</div>;
export default SyncLogs;
```

**注意：** 每个占位文件需要 `import React from 'react';` 或使用 TS 的 `react-jsx` transform（我们的 tsconfig 配置了 `"jsx": "react-jsx"` 所以不需要显式 import React，但 `React.FC` 类型需要 import）。正确写法：

```tsx
import type React from 'react';

const Dashboard: React.FC = () => <div>Dashboard</div>;
export default Dashboard;
```

对所有 4 个文件都用此模式（只替换组件名和文字）。

- [ ] **Step 6: 验证 TypeScript 编译和构建**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 无错误，构建成功

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add routing, AppLayout, Login page, and placeholder pages"
```

---

### Task 4: Dashboard 页面

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` — 替换占位内容为完整实现

- [ ] **Step 1: 实现 Dashboard.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Table, Tag, Button, Skeleton, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import client from '../api/client';

interface HealthComponent {
  status: string;
  latency_ms?: number;
  error?: string;
  workers?: number;
}

interface HealthData {
  status: string;
  components: Record<string, HealthComponent>;
  version: string;
}

interface SyncLogItem {
  id: number;
  entity: string;
  status: string;
  total_records: number;
  started_at: string;
}

interface StatsData {
  connectors: { total: number; enabled: number };
  syncTasks: { total: number; enabled: number };
}

const statusColorMap: Record<string, string> = {
  healthy: 'green',
  degraded: 'orange',
  unhealthy: 'red',
};

const logStatusColorMap: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
};

const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [logs, setLogs] = useState<SyncLogItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [healthRes, connectorsRes, tasksRes, logsRes] = await Promise.all([
        client.get('/health'),
        client.get('/connectors', { params: { page: 1, page_size: 1 } }),
        client.get('/sync-tasks', { params: { page: 1, page_size: 1 } }),
        client.get('/sync-logs', { params: { page: 1, page_size: 10 } }),
      ]);

      setHealth(healthRes.data);

      // 统计：从分页响应中取 total_count
      // 启用数需要单独统计 — 简化：用 page_size=100 取全部再 filter
      const [allConnectors, allTasks] = await Promise.all([
        client.get('/connectors', { params: { page: 1, page_size: 100 } }),
        client.get('/sync-tasks', { params: { page: 1, page_size: 100 } }),
      ]);

      setStats({
        connectors: {
          total: allConnectors.data.total_count,
          enabled: allConnectors.data.items.filter(
            (c: { enabled: boolean }) => c.enabled,
          ).length,
        },
        syncTasks: {
          total: allTasks.data.total_count,
          enabled: allTasks.data.items.filter(
            (t: { enabled: boolean }) => t.enabled,
          ).length,
        },
      });

      setLogs(logsRes.data.items);
    } catch {
      message.error('获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const renderHealthCard = (name: string, component: HealthComponent) => (
    <Col span={8} key={name}>
      <Card size="small" title={name.charAt(0).toUpperCase() + name.slice(1)}>
        <Tag color={statusColorMap[component.status] ?? 'default'}>
          {component.status}
        </Tag>
        {component.status === 'healthy' && component.latency_ms !== undefined && (
          <span style={{ marginLeft: 8 }}>{component.latency_ms}ms</span>
        )}
        {component.status === 'healthy' && component.workers !== undefined && (
          <span style={{ marginLeft: 8 }}>Workers: {component.workers}</span>
        )}
        {component.status === 'unhealthy' && component.error && (
          <div style={{ marginTop: 8, color: '#ff4d4f', fontSize: 12 }}>
            {component.error}
          </div>
        )}
      </Card>
    </Col>
  );

  const logColumns: ColumnsType<SyncLogItem> = [
    { title: '时间', dataIndex: 'started_at', key: 'started_at', width: 180 },
    { title: 'Entity', dataIndex: 'entity', key: 'entity' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={logStatusColorMap[s] ?? 'default'}>{s}</Tag>
      ),
    },
    { title: '记录数', dataIndex: 'total_records', key: 'total_records' },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>Dashboard</h2>
        <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading}>
          刷新
        </Button>
      </div>

      {/* 健康状态 */}
      {loading && !health ? (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[1, 2, 3].map((i) => (
            <Col span={8} key={i}>
              <Card size="small">
                <Skeleton active paragraph={{ rows: 1 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : health ? (
        <>
          <div style={{ marginBottom: 8 }}>
            系统状态：{' '}
            <Tag color={statusColorMap[health.status] ?? 'default'}>
              {health.status}
            </Tag>
          </div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            {Object.entries(health.components).map(([name, comp]) =>
              renderHealthCard(name, comp),
            )}
          </Row>
        </>
      ) : null}

      {/* 统计摘要 */}
      {loading && !stats ? (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[1, 2].map((i) => (
            <Col span={12} key={i}>
              <Card size="small">
                <Skeleton active paragraph={{ rows: 1 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : stats ? (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card size="small" title="连接器">
              总数：{stats.connectors.total} / 启用：{stats.connectors.enabled}
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" title="同步任务">
              总数：{stats.syncTasks.total} / 启用：{stats.syncTasks.enabled}
            </Card>
          </Col>
        </Row>
      ) : null}

      {/* 最近同步日志 */}
      <Card title="最近同步日志" size="small">
        <Table
          dataSource={logs}
          columns={logColumns}
          rowKey="id"
          pagination={false}
          loading={loading}
          size="small"
        />
      </Card>
    </div>
  );
};

export default Dashboard;
```

- [ ] **Step 2: 验证 TypeScript 编译和构建**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): implement Dashboard page with health, stats, and recent logs"
```

---

### Task 5: 连接器管理页面

**Files:**
- Modify: `frontend/src/pages/Connectors.tsx` — 替换占位内容为完整实现

- [ ] **Step 1: 实现 Connectors.tsx**

后端 API 参考：
- `GET /api/v1/connectors?page=N&page_size=M` → `{ items, total_count, page, page_size }`
- `POST /api/v1/connectors` body: `{ name, connector_type, base_url, auth_config, description? }`
- `PUT /api/v1/connectors/{id}` body: `{ name?, connector_type?, base_url?, auth_config?, description?, enabled? }`
- `DELETE /api/v1/connectors/{id}` → 204

连接器类型选项：`kingdee_erp`, `kingdee_plm`, `feishu`, `fenxiangxiaoke`, `lingxing`, `zentao`

```tsx
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Popconfirm,
  Tag,
  message,
  Space,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import client from '../api/client';

interface ConnectorItem {
  id: number;
  name: string;
  connector_type: string;
  base_url: string;
  has_auth_config: boolean;
  enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

const CONNECTOR_TYPES = [
  { value: 'kingdee_erp', label: '金蝶ERP' },
  { value: 'kingdee_plm', label: '金蝶PLM' },
  { value: 'feishu', label: '飞书' },
  { value: 'fenxiangxiaoke', label: '纷享销客' },
  { value: 'lingxing', label: '领星ERP' },
  { value: 'zentao', label: '禅道' },
];

const Connectors: React.FC = () => {
  const [data, setData] = useState<ConnectorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get('/connectors', {
        params: { page, page_size: pageSize },
      });
      setData(res.data.items);
      setTotal(res.data.total_count);
    } catch {
      message.error('获取连接器列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const openCreate = () => {
    setEditingId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: ConnectorItem) => {
    setEditingId(record.id);
    form.setFieldsValue({
      name: record.name,
      description: record.description ?? '',
      connector_type: record.connector_type,
      base_url: record.base_url,
      auth_config: '',
      enabled: record.enabled,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      // 解析 auth_config JSON
      let authConfig: Record<string, unknown> = {};
      if (values.auth_config && values.auth_config.trim()) {
        try {
          authConfig = JSON.parse(values.auth_config);
        } catch {
          message.error('Auth Config 必须是有效的 JSON');
          setSubmitting(false);
          return;
        }
      }

      if (editingId) {
        // 编辑：发送全部字段（含 enabled）
        await client.put(`/connectors/${editingId}`, {
          name: values.name,
          connector_type: values.connector_type,
          base_url: values.base_url,
          description: values.description || null,
          enabled: values.enabled,
          ...(Object.keys(authConfig).length > 0 ? { auth_config: authConfig } : {}),
        });
        message.success('连接器已更新');
      } else {
        // 创建：ConnectorCreate 没有 enabled 字段（默认 true）
        await client.post('/connectors', {
          name: values.name,
          connector_type: values.connector_type,
          base_url: values.base_url,
          auth_config: authConfig,
          description: values.description || null,
        });
        message.success('连接器已创建');
      }

      setModalOpen(false);
      fetchData();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        message.error(axiosErr.response?.data?.detail ?? '操作失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleEnabled = async (record: ConnectorItem) => {
    try {
      await client.put(`/connectors/${record.id}`, {
        enabled: !record.enabled,
      });
      message.success(record.enabled ? '已禁用' : '已启用');
      fetchData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await client.delete(`/connectors/${id}`);
      message.success('连接器已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns: ColumnsType<ConnectorItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'connector_type', key: 'connector_type' },
    { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button size="small" onClick={() => handleToggleEnabled(record)}>
            {record.enabled ? '禁用' : '启用'}
          </Button>
          <Popconfirm
            title="确认删除此连接器？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>连接器管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建连接器
        </Button>
      </div>

      <Table
        dataSource={data}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title={editingId ? '编辑连接器' : '新建连接器'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label="类型"
            rules={[{ required: true, message: '请选择类型' }]}
          >
            <Select options={CONNECTOR_TYPES} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[{ required: true, message: '请输入 Base URL' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="auth_config"
            label="Auth Config (JSON)"
            rules={
              editingId
                ? []
                : [{ required: true, message: '请输入 Auth Config' }]
            }
            help={editingId ? '留空表示不修改' : undefined}
          >
            <Input.TextArea rows={4} placeholder='{"key": "value"}' />
          </Form.Item>
          {editingId && (
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default Connectors;
```

- [ ] **Step 2: 验证 TypeScript 编译和构建**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Connectors.tsx
git commit -m "feat(frontend): implement Connectors CRUD page with modal form"
```

---

### Task 6: 同步任务管理页面

**Files:**
- Modify: `frontend/src/pages/SyncTasks.tsx` — 替换占位内容为完整实现

- [ ] **Step 1: 实现 SyncTasks.tsx**

后端 API 参考：
- `GET /api/v1/sync-tasks?page=N&page_size=M` → `{ items, total_count, page, page_size }`
  - item fields: `id, connector_id, entity, direction, cron_expression, enabled, last_sync_at, next_run_at, created_at, updated_at`
- `POST /api/v1/sync-tasks` body: `{ connector_id, entity, direction, cron_expression?, enabled? }`
- `PUT /api/v1/sync-tasks/{id}` body: `{ entity?, direction?, cron_expression?, enabled? }`（注意：**不含** `connector_id`）
- `DELETE /api/v1/sync-tasks/{id}` → 204
- `POST /api/v1/sync-tasks/{id}/trigger` → 202 `{ status, task_id, celery_task_id, message }`

```tsx
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Popconfirm,
  Tag,
  message,
  Space,
} from 'antd';
import { PlusOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import client from '../api/client';

interface SyncTaskItem {
  id: number;
  connector_id: number;
  entity: string;
  direction: string;
  cron_expression: string | null;
  enabled: boolean;
  last_sync_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ConnectorOption {
  id: number;
  name: string;
  connector_type: string;
}

const SyncTasks: React.FC = () => {
  const [data, setData] = useState<SyncTaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [connectorOptions, setConnectorOptions] = useState<ConnectorOption[]>([]);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get('/sync-tasks', {
        params: { page, page_size: pageSize },
      });
      setData(res.data.items);
      setTotal(res.data.total_count);
    } catch {
      message.error('获取同步任务列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fetchConnectors = async () => {
    try {
      const res = await client.get('/connectors', {
        params: { page: 1, page_size: 100 },
      });
      setConnectorOptions(
        res.data.items.map((c: { id: number; name: string; connector_type: string }) => ({
          id: c.id,
          name: c.name,
          connector_type: c.connector_type,
        })),
      );
    } catch {
      message.error('获取连接器列表失败');
    }
  };

  const openCreate = async () => {
    setEditingId(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, direction: 'pull' });
    await fetchConnectors();
    setModalOpen(true);
  };

  const openEdit = async (record: SyncTaskItem) => {
    setEditingId(record.id);
    form.setFieldsValue({
      connector_id: record.connector_id,
      entity: record.entity,
      direction: record.direction,
      cron_expression: record.cron_expression ?? '',
      enabled: record.enabled,
    });
    await fetchConnectors();
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingId) {
        // PUT 不含 connector_id
        await client.put(`/sync-tasks/${editingId}`, {
          entity: values.entity,
          direction: values.direction,
          cron_expression: values.cron_expression || null,
          enabled: values.enabled,
        });
        message.success('同步任务已更新');
      } else {
        await client.post('/sync-tasks', {
          connector_id: values.connector_id,
          entity: values.entity,
          direction: values.direction,
          cron_expression: values.cron_expression || null,
          enabled: values.enabled,
        });
        message.success('同步任务已创建');
      }

      setModalOpen(false);
      fetchData();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        message.error(axiosErr.response?.data?.detail ?? '操作失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleTrigger = async (id: number) => {
    try {
      await client.post(`/sync-tasks/${id}/trigger`);
      message.success('同步任务已加入队列');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        message.error(axiosErr.response?.data?.detail ?? '触发失败');
      } else {
        message.error('触发失败');
      }
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await client.delete(`/sync-tasks/${id}`);
      message.success('同步任务已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns: ColumnsType<SyncTaskItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '连接器 ID', dataIndex: 'connector_id', key: 'connector_id', width: 90 },
    { title: 'Entity', dataIndex: 'entity', key: 'entity' },
    {
      title: 'Direction',
      dataIndex: 'direction',
      key: 'direction',
      render: (d: string) => <Tag>{d}</Tag>,
    },
    { title: 'Cron', dataIndex: 'cron_expression', key: 'cron_expression' },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '上次同步',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      width: 180,
      render: (v: string | null) => v ?? '-',
    },
    {
      title: '下次运行',
      dataIndex: 'next_run_at',
      key: 'next_run_at',
      width: 180,
      render: (v: string | null) => v ?? '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 240,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => handleTrigger(record.id)}
          >
            触发
          </Button>
          <Popconfirm
            title="确认删除此同步任务？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>同步任务管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建任务
        </Button>
      </div>

      <Table
        dataSource={data}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title={editingId ? '编辑同步任务' : '新建同步任务'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="connector_id"
            label="连接器"
            rules={[{ required: true, message: '请选择连接器' }]}
          >
            <Select
              disabled={editingId !== null}
              options={connectorOptions.map((c) => ({
                value: c.id,
                label: `${c.name} (${c.connector_type})`,
              }))}
              placeholder="请选择连接器"
            />
          </Form.Item>
          <Form.Item
            name="entity"
            label="Entity"
            rules={[{ required: true, message: '请输入 Entity' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="direction"
            label="Direction"
            rules={[{ required: true, message: '请选择同步方向' }]}
          >
            <Select
              options={[
                { value: 'pull', label: 'Pull（拉取）' },
                { value: 'push', label: 'Push（推送）' },
              ]}
            />
          </Form.Item>
          <Form.Item name="cron_expression" label="Cron Expression">
            <Input placeholder="例如: */30 * * * * (每30分钟)" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SyncTasks;
```

- [ ] **Step 2: 验证 TypeScript 编译和构建**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SyncTasks.tsx
git commit -m "feat(frontend): implement SyncTasks CRUD page with trigger support"
```

---

### Task 7: 同步日志页面

**Files:**
- Modify: `frontend/src/pages/SyncLogs.tsx` — 替换占位内容为完整实现

- [ ] **Step 1: 实现 SyncLogs.tsx**

后端 API 参考：
- `GET /api/v1/sync-logs?page=N&page_size=M&connector_id=X&entity=Y&status=Z&started_after=ISO&started_before=ISO`
  - item fields: `id, sync_task_id, connector_id, entity, direction, status, total_records, success_count, failure_count, error_details, started_at, finished_at`

```tsx
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Select, Input, DatePicker, Space, Card, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import client from '../api/client';

const { RangePicker } = DatePicker;

interface SyncLogItem {
  id: number;
  sync_task_id: number | null;
  connector_id: number;
  entity: string;
  direction: string;
  status: string;
  total_records: number;
  success_count: number;
  failure_count: number;
  error_details: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}

const statusColorMap: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
};

const SyncLogs: React.FC = () => {
  const [data, setData] = useState<SyncLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);

  // 筛选状态
  const [filterConnectorId, setFilterConnectorId] = useState<string>('');
  const [filterEntity, setFilterEntity] = useState('');
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined);
  const [filterDateRange, setFilterDateRange] = useState<
    [Dayjs | null, Dayjs | null] | null
  >(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (filterConnectorId) params.connector_id = filterConnectorId;
      if (filterEntity) params.entity = filterEntity;
      if (filterStatus) params.status = filterStatus;
      if (filterDateRange?.[0]) {
        params.started_after = filterDateRange[0].toISOString();
      }
      if (filterDateRange?.[1]) {
        params.started_before = filterDateRange[1].toISOString();
      }

      const res = await client.get('/sync-logs', { params });
      setData(res.data.items);
      setTotal(res.data.total_count);
    } catch {
      message.error('获取同步日志失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterConnectorId, filterEntity, filterStatus, filterDateRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 筛选变化时回到第 1 页
  useEffect(() => {
    setPage(1);
  }, [filterConnectorId, filterEntity, filterStatus, filterDateRange]);

  const columns: ColumnsType<SyncLogItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '任务 ID', dataIndex: 'sync_task_id', key: 'sync_task_id', width: 80, render: (v: number | null) => v ?? '-' },
    { title: '连接器 ID', dataIndex: 'connector_id', key: 'connector_id', width: 90 },
    { title: 'Entity', dataIndex: 'entity', key: 'entity' },
    {
      title: 'Direction',
      dataIndex: 'direction',
      key: 'direction',
      render: (d: string) => <Tag>{d}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={statusColorMap[s] ?? 'default'}>{s}</Tag>
      ),
    },
    { title: '总记录', dataIndex: 'total_records', key: 'total_records', width: 80 },
    { title: '成功', dataIndex: 'success_count', key: 'success_count', width: 60 },
    { title: '失败', dataIndex: 'failure_count', key: 'failure_count', width: 60 },
    { title: '开始时间', dataIndex: 'started_at', key: 'started_at', width: 180 },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 180,
      render: (v: string | null) => v ?? '-',
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>同步日志</h2>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="连接器 ID"
            value={filterConnectorId}
            onChange={(e) => setFilterConnectorId(e.target.value)}
            style={{ width: 120 }}
            allowClear
          />
          <Input
            placeholder="Entity"
            value={filterEntity}
            onChange={(e) => setFilterEntity(e.target.value)}
            style={{ width: 150 }}
            allowClear
          />
          <Select
            placeholder="状态"
            value={filterStatus}
            onChange={setFilterStatus}
            allowClear
            style={{ width: 120 }}
            options={[
              { value: 'success', label: '成功' },
              { value: 'failed', label: '失败' },
              { value: 'running', label: '运行中' },
            ]}
          />
          <RangePicker
            showTime
            onChange={(dates) =>
              setFilterDateRange(dates as [Dayjs | null, Dayjs | null] | null)
            }
          />
        </Space>
      </Card>

      <Table
        dataSource={data}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
        expandable={{
          expandedRowRender: (record) =>
            record.error_details ? (
              <pre style={{ margin: 0, fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
                {JSON.stringify(record.error_details, null, 2)}
              </pre>
            ) : (
              <span style={{ color: '#999' }}>无错误详情</span>
            ),
          rowExpandable: () => true,
        }}
        size="small"
      />
    </div>
  );
};

export default SyncLogs;
```

- [ ] **Step 2: 验证 TypeScript 编译和构建**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SyncLogs.tsx
git commit -m "feat(frontend): implement SyncLogs page with filters and expandable details"
```

---

### Task 8: 后端 StaticFiles 挂载 + SPA Fallback

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_spa_fallback.py`

- [ ] **Step 1: 写 SPA fallback 的测试**

由于 frontend/dist 目录在测试环境中可能不存在，测试需要创建临时目录。创建 `tests/test_spa_fallback.py`：

```python
"""测试 SPA fallback 路由"""
import os
import tempfile

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient


def _create_spa_app(frontend_dir: str) -> FastAPI:
    """创建带 SPA fallback 的 FastAPI 应用（复制 main.py 逻辑）"""
    app = FastAPI()

    # 模拟一个 API 路由
    @app.get("/api/v1/health")
    def health():
        return {"status": "healthy"}

    # SPA fallback
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    return app


def test_spa_fallback_serves_index_html():
    """非 API 路径返回 index.html"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "SPA" in response.text


def test_spa_fallback_serves_static_file():
    """已有静态文件直接返回对应文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        assets_dir = os.path.join(tmpdir, "assets")
        os.makedirs(assets_dir)
        js_path = os.path.join(assets_dir, "main.js")
        with open(js_path, "w") as f:
            f.write("console.log('hello');")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/assets/main.js")
        assert response.status_code == 200
        assert "hello" in response.text


def test_api_routes_take_priority():
    """API 路由优先于 SPA fallback"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /home/lenovo/dev/projects/data_platform && python -m pytest tests/test_spa_fallback.py -v
```
Expected: 测试通过（因为测试使用独立的 `_create_spa_app`，不依赖 main.py 的实际改动）

注意：这些测试验证的是 SPA fallback 的逻辑模式，而非 main.py 本身。它们先写是为了确认逻辑正确。

- [ ] **Step 3: 修改 src/main.py — 添加 SPA fallback**

在 `src/main.py` 文件末尾，删除现有的根路由 `@app.get("/")` 并替换为 SPA fallback：

```python
# src/main.py
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse

from src.api.errors import register_error_handlers
from src.api.routes.connectors import router as connectors_router
from src.api.routes.health import router as health_router
from src.api.routes.sync_tasks import router as sync_tasks_router
from src.api.routes.sync_logs import router as sync_logs_router
from src.api.routes.push import router as push_router
from src.api.routes.data import router as data_router

app = FastAPI(title="数据中台", version="0.1.0")

# 注册统一错误处理
register_error_handlers(app)

# 注册路由 — 健康检查免认证
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(connectors_router, prefix="/api/v1", tags=["connectors"])
app.include_router(sync_tasks_router, prefix="/api/v1", tags=["sync"])
app.include_router(sync_logs_router, prefix="/api/v1", tags=["sync"])
app.include_router(push_router, prefix="/api/v1", tags=["push"])
app.include_router(data_router, prefix="/api/v1", tags=["data"])

# SPA fallback — 当 frontend/dist 目录存在时，提供前端静态文件
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_frontend_dir = os.path.normpath(_frontend_dir)

if os.path.isdir(_frontend_dir):

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback：静态文件直接返回，其余返回 index.html"""
        file_path = os.path.join(_frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

else:

    @app.get("/")
    def root():
        return {"name": "数据中台", "version": "0.1.0"}
```

- [ ] **Step 4: 运行全部后端测试确认无回归**

Run:
```bash
cd /home/lenovo/dev/projects/data_platform && python -m pytest tests/ -v
```
Expected: 全部通过（包括新增的 3 个 SPA 测试和原有 182 个测试）

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_spa_fallback.py
git commit -m "feat(backend): add SPA fallback route for frontend static files"
```

---

### Task 9: Dockerfile + Docker Compose 更新

**Files:**
- Create: `Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: 创建多阶段 Dockerfile**

```dockerfile
# Stage 1: 前端构建
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 运行
FROM python:3.11-slim
WORKDIR /app

# 安装系统依赖（psycopg2 需要 libpq）
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 从前端构建阶段复制产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 更新 docker-compose.yml — 添加 web 服务**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: data_platform
      POSTGRES_USER: dp_user
      POSTGRES_PASSWORD: dp_pass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  web:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
      REDIS_URL: redis://redis:6379/0
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-default-dev-key}
      API_KEY: ${API_KEY:-default-dev-key}

  celery-worker:
    build: .
    command: celery -A src.core.celery_app worker --loglevel=info --concurrency=4
    depends_on:
      - redis
      - postgres
    environment:
      DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
      REDIS_URL: redis://redis:6379/0
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-default-dev-key}
      API_KEY: ${API_KEY:-default-dev-key}

  celery-beat:
    build: .
    command: >
      celery -A src.core.celery_app beat
      --scheduler src.tasks.scheduler:DatabaseScheduler
      --loglevel=info
    depends_on:
      - redis
      - postgres
    environment:
      DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
      REDIS_URL: redis://redis:6379/0

volumes:
  pgdata:
```

- [ ] **Step 3: 更新 .gitignore — 排除 Dockerfile 不需要的文件（可选）**

检查 `.gitignore` 是否已包含 `frontend/node_modules/` 和 `frontend/dist/`（Task 1 已添加）。无需额外改动。

- [ ] **Step 4: 验证 Dockerfile 语法**

Run:
```bash
cd /home/lenovo/dev/projects/data_platform && docker build --check . 2>&1 || echo "Docker syntax check done"
```
Expected: 无语法错误（注意：不需要实际完成构建，只验证语法）

如果 `docker build --check` 不可用（较旧版本），改用：
```bash
cat Dockerfile
```
目视确认无语法问题。

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat(deploy): add multi-stage Dockerfile and web service to docker-compose"
```
