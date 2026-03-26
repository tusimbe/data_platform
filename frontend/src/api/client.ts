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
