// 路由：登录页 /auth + 登录后首页 / （需要鉴权）
import { createRouter, createWebHistory } from 'vue-router'
import Auth from '../views/Auth.vue'
import Gallery from '../views/Gallery.vue'   // ✅ 登陆后的页面
import { isTokenValid } from '../utils/jwt'   // 验证登录页面是否过期
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',      name: 'gallery', component: Gallery, meta: { auth: true } }, // 需要登录
    { path: '/auth',  name: 'auth',    component: Auth },                          // 登录/注册
    { path: '/:pathMatch(.*)*', redirect: '/' },                                   // 兜底
  ],
})

// ✅ 简单路由守卫：未登录不能进需要鉴权的页面；已登录访问 /auth 则跳回 /
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  const authed = isTokenValid(token)
  if (to.meta?.auth && !token) {
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  if (to.meta?.auth && !authed) {
    localStorage.removeItem('access_token')                  // 失效就清理
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  
  if (to.path === '/auth' && token) {
    return { path: '/' }
  }
})

export default router

//cd "$ROOT"
//git add database docker-compose.yml server
//git commit -m "feat: MySQL schema (users with avatar_url, images) + PyMySQL auth endpoints"
//git push