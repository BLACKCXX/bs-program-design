// Axios 实例：统一 baseURL、Token 注入、错误拦截
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 10000,
})

// 请求拦截：附带本地存储的 JWT（后端准备好后可直连）
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：错误统一 toast（也可在调用处自定义）
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err?.response?.data?.error || err.message || '网络异常'
    // 简单输出；你也可以用 Element Plus 的 ElMessage
    console.error('[API ERROR]', msg)
    return Promise.reject(err)
  }
)

export default api
