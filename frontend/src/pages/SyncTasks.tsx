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
        const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
        message.error(axiosErr.response?.data?.error?.message ?? axiosErr.response?.data?.detail ?? '操作失败');
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
        const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
        message.error(axiosErr.response?.data?.error?.message ?? axiosErr.response?.data?.detail ?? '触发失败');
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
