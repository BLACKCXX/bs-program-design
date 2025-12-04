// 入口：挂载 Vue 应用、注册 Pinia 与 Element Plus
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

// 可在此引入全局样式（为了简洁，直接写在 App.vue）
createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
