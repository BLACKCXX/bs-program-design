// 导航结构：使用主布局 + 子路由，保留原有权限校验
import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import Auth from '../views/Auth.vue'
import Gallery from '../views/Gallery.vue'   // 首页
import ImageDetail from '../views/ImageDetail.vue' // 图片详情
import SearchEngine from '../views/SearchEngine.vue'
import UploadCenter from '../views/UploadCenter.vue'
import AiWorkspace from '../views/AiWorkspace.vue'
import { isTokenValid } from '../utils/jwt'   // 简单 token 校验

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      meta: { auth: true },
      children: [
        { path: '', name: 'gallery', component: Gallery, meta: { auth: true } },
        { path: 'home', redirect: { name: 'gallery' } },
        { path: 'search', name: 'search', component: SearchEngine, meta: { auth: true } },
        { path: 'upload', name: 'upload', component: UploadCenter, meta: { auth: true } },
        { path: 'ai', name: 'ai', component: AiWorkspace, meta: { auth: true } },
        { path: 'images/:id', name: 'ImageDetail', component: ImageDetail, meta: { auth: true } },
      ],
    },
    { path: '/auth', name: 'auth', component: Auth }, // 登陆/注册
    { path: '/:pathMatch(.*)*', redirect: '/' }, // 兜底
  ],
})

// 简单的登录校验：未登录访问受保护页面时跳转 /auth，已登录访问 /auth 时回首页
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  const authed = isTokenValid(token)
  if (to.meta?.auth && !token) {
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  if (to.meta?.auth && !authed) {
    localStorage.removeItem('access_token') // token 过期清除
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  if (to.path === '/auth' && token) {
    return { path: '/' }
  }
})

export default router
