import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Table, Tag, Button, Skeleton, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import client from '../api/client';
import { SyncLogItem } from '../types/api';

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
      const [healthRes, , , logsRes] = await Promise.all([
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
