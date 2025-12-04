// 认证 Store：封装登录/注册/登出
import { defineStore } from 'pinia'
import api from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('access_token') || null,
  }),
  actions: {
    async login(identifier, password) {
      // identifier: 邮箱或用户名（后端就绪后你可以兼容两种）
      const payload = identifier.includes('@')
        ? { email: identifier, password }
        : { username: identifier, password }

      // 这里演示命中 /api/auth/login（后端未就绪时会 404）
      const { data } = await api.post('/api/auth/login', payload)
      this.user = data.user
      this.token = data.access_token
      localStorage.setItem('access_token', this.token)
    },
    async register(email, username, password) {
      const { data } = await api.post('/api/auth/register', { email, username, password })
      this.user = data.user
      this.token = data.access_token
      localStorage.setItem('access_token', this.token)
    },
    logout() {
      this.user = null
      this.token = null
      localStorage.removeItem('access_token')
    }
  }
})
