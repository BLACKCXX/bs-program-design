<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { House, Search, UploadFilled, MagicStick } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const menuItems = [
  { label: '首页', name: 'gallery', icon: House },
  { label: '搜索引擎', name: 'search', icon: Search },
  { label: '上传中心', name: 'upload', icon: UploadFilled },
  { label: 'AI 工作台', name: 'ai', icon: MagicStick },
]

const activeName = computed(() => {
  if (route.name === 'ImageDetail') return 'gallery'
  return route.name
})

const go = (item) => {
  if (item.name && item.name !== route.name) {
    router.push({ name: item.name })
  }
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo">P</div>
        <div>
          <div class="brand-name">Private Picture Shop</div>
          <div class="brand-desc">Private Picture Shop 你的私人图片小铺~</div>
        </div>
      </div>

      <nav class="menu">
        <button
          v-for="item in menuItems"
          :key="item.name"
          class="menu-item"
          :class="{ active: activeName === item.name }"
          @click="go(item)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <main class="content">
      <div class="content-inner">
        <router-view />
      </div>
    </main>
  </div>
</template>

<style scoped>
.layout {
  --primary: var(--app-primary);
  --primary-soft: var(--app-primary-soft);
  --text-main: var(--app-text);
  --text-muted: var(--app-muted);
  display: flex;
  min-height: 100vh;
  background: linear-gradient(180deg, #f7f9fc, #eef3fb);
}

.sidebar {
  width: 230px;
  background: #f5f7ff;
  border-right: 1px solid var(--app-border);
  box-shadow: 4px 0 22px rgba(75, 140, 255, 0.08);
  padding: 22px 18px;
  position: sticky;
  top: 0;
  height: 100vh;
  box-sizing: border-box;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
}

.brand-logo {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #6ca5ff, #4b8cff);
  color: #fff;
  font-weight: 800;
  font-size: 20px;
  box-shadow: 0 10px 24px rgba(75, 140, 255, 0.25);
}

.brand-name {
  font-weight: 800;
  font-size: 18px;
  color: var(--text-main);
}

.brand-desc {
  color: var(--text-muted);
  font-size: 13px;
}

.menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.menu-item {
  width: 100%;
  border: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px;
  border-radius: 12px;
  background: transparent;
  color: #374151;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}

.menu-item:hover {
  background: var(--primary-soft);
}

.menu-item.active {
  background: var(--primary-soft);
  color: var(--primary);
  box-shadow: inset 0 0 0 1px rgba(75, 140, 255, 0.18);
  border-left: 4px solid var(--primary);
  padding-left: 8px;
}

.menu-item :deep(.el-icon) {
  font-size: 18px;
}

.content {
  flex: 1;
  min-height: 100vh;
  background: #f4f7fb;
  overflow-y: auto;
}

.content-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 18px 22px 28px;
  box-sizing: border-box;
}

@media (max-width: 900px) {
  .sidebar {
    width: 190px;
    padding: 18px 14px;
  }

  .menu-item {
    padding: 10px;
  }
}
</style>
