import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Select, Input, DatePicker, Space, Card, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import client from '../api/client';
import { SyncLogItem } from '../types/api';

const { RangePicker } = DatePicker;

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

  const [debouncedConnectorId, setDebouncedConnectorId] = useState('');
  const [debouncedEntity, setDebouncedEntity] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedConnectorId(filterConnectorId), 300);
    return () => clearTimeout(timer);
  }, [filterConnectorId]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedEntity(filterEntity), 300);
    return () => clearTimeout(timer);
  }, [filterEntity]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (debouncedConnectorId) params.connector_id = debouncedConnectorId;
      if (debouncedEntity) params.entity = debouncedEntity;
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
  }, [page, pageSize, debouncedConnectorId, debouncedEntity, filterStatus, filterDateRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
            onChange={(e) => { setFilterConnectorId(e.target.value); setPage(1); }}
            style={{ width: 120 }}
            allowClear
          />
          <Input
            placeholder="Entity"
            value={filterEntity}
            onChange={(e) => { setFilterEntity(e.target.value); setPage(1); }}
            style={{ width: 150 }}
            allowClear
          />
          <Select
            placeholder="状态"
            value={filterStatus}
            onChange={(v) => { setFilterStatus(v); setPage(1); }}
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
            onChange={(dates) => {
              setFilterDateRange(dates as [Dayjs | null, Dayjs | null] | null);
              setPage(1);
            }}
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
