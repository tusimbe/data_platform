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
        const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
        message.error(axiosErr.response?.data?.error?.message ?? axiosErr.response?.data?.detail ?? '操作失败');
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
