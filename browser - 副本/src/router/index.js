// ?????? /auth + ????? / ??????
import { createRouter, createWebHistory } from 'vue-router'
import Auth from '../views/Auth.vue'
import Gallery from '../views/Gallery.vue'   // ??????
import ImageDetail from '../views/ImageDetail.vue' // ???????
import { isTokenValid } from '../utils/jwt'   // ??????????

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'gallery', component: Gallery, meta: { auth: true } }, // ????
    // ???????????????
    { path: '/images/:id', name: 'ImageDetail', component: ImageDetail, meta: { auth: true } },
    { path: '/auth', name: 'auth', component: Auth }, // ??/??
    { path: '/:pathMatch(.*)*', redirect: '/' }, // ??
  ],
})

// ???????????????????????? /auth ??? /
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  const authed = isTokenValid(token)
  if (to.meta?.auth && !token) {
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  if (to.meta?.auth && !authed) {
    localStorage.removeItem('access_token') // ?????
    return { path: '/auth', query: { redirect: to.fullPath } }
  }
  if (to.path === '/auth' && token) {
    return { path: '/' }
  }
})

export default router
