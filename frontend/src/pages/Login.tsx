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
