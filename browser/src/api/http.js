// Axios 实例：同源相对路径，请求统一注入 Token + 友好错误日志
import axios from 'axios'

const api = axios.create({
  baseURL: '/', // 使用相对路径，便于 PC localhost 与手机通过局域网 IP 同源访问
  withCredentials: false,
  timeout: 10000,
})

// 请求拦截：附带本地存储的 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：区分网络错误与业务错误，避免误判“后端未就绪”
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const path = err?.config?.url || ''
    if (err?.response) {
      const status = err.response.status
      const detail = err.response.data?.error || err.response.data?.message || err.message || '请求失败'
      console.error(`[API ERROR] ${path} -> ${status} ${detail}`)
    } else {
      console.error(`[API ERROR] ${path || 'request'} -> 网络连接失败，请检查后端/代理`, err?.message)
    }
    return Promise.reject(err)
  }
)

export default api
