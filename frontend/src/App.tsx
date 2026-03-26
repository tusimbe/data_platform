import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
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
    <ErrorBoundary>
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
    </ErrorBoundary>
  </BrowserRouter>
);

export default App;
