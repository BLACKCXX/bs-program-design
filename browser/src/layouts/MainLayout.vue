<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { House, Search, UploadFilled, MagicStick, Menu as MenuIcon } from '@element-plus/icons-vue'

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

const isMobile = ref(false)
const drawerVisible = ref(false)

const detectMobile = () => {
  if (typeof window === 'undefined') return
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
  if (!isMobile.value) {
    drawerVisible.value = false
  }
}

const go = (item) => {
  if (item.name && item.name !== route.name) {
    router.push({ name: item.name })
  }
  if (isMobile.value) {
    drawerVisible.value = false
  }
}

// 桌面端悬停展开的状态
const expanded = ref(false)
let collapseTimer = null
const expand = () => {
  clearTimeout(collapseTimer)
  expanded.value = true
}
const scheduleCollapse = () => {
  clearTimeout(collapseTimer)
  collapseTimer = setTimeout(() => (expanded.value = false), 200)
}
const toggleManual = () => {
  clearTimeout(collapseTimer)
  expanded.value = !expanded.value
}

onMounted(() => {
  detectMobile()
  window.addEventListener('resize', detectMobile)
})

onBeforeUnmount(() => {
  clearTimeout(collapseTimer)
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', detectMobile)
  }
})
</script>

<template>
  <div class="layout" :class="{ mobile: isMobile, expanded: expanded && !isMobile, collapsed: !expanded && !isMobile }">
    <aside
      v-if="!isMobile"
      class="sidebar"
      :class="{ expanded }"
      @mouseenter="expand"
      @mouseleave="scheduleCollapse"
    >
      <div class="brand">
        <div class="brand-logo">P</div>
        <div class="brand-text">
          <div class="brand-name">Private Picture Shop</div>
          <div class="brand-desc">你的私人图片小铺~</div>
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
          <span class="menu-label">{{ item.label }}</span>
        </button>
      </nav>

      <button class="sidebar-toggle" type="button" @click="toggleManual" aria-label="切换导航栏展开">
        <el-icon><component :is="expanded ? UploadFilled : House" /></el-icon>
      </button>
    </aside>

    <el-drawer
      v-model="drawerVisible"
      direction="ltr"
      size="260px"
      :with-header="false"
      class="mobile-drawer"
    >
      <div class="drawer-body">
        <div class="brand brand-mobile">
          <div class="brand-logo">P</div>
          <div class="brand-text">
            <div class="brand-name">Private Picture Shop</div>
            <div class="brand-desc">随时随地浏览</div>
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
            <span class="menu-label">{{ item.label }}</span>
          </button>
        </nav>
      </div>
    </el-drawer>

    <main class="content">
      <header v-if="isMobile" class="mobile-topbar">
        <button class="menu-button" type="button" @click="drawerVisible = true" aria-label="打开主导航">
          <el-icon><MenuIcon /></el-icon>
        </button>
        <div class="mobile-brand">
          <span class="brand-logo">P</span>
          <div class="brand-text">
            <div class="brand-name">Private Picture Shop</div>
            <div class="brand-desc">图片管理</div>
          </div>
        </div>
        <div class="topbar-spacer" aria-hidden="true"></div>
      </header>
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
  --sidebar-collapsed: 72px;
  --sidebar-expanded: 240px;
  --sidebar-w: var(--sidebar-collapsed);
  display: flex;
  min-height: 100vh;
  background: linear-gradient(180deg, #f7f9fc, #eef3fb);
}

.layout.expanded {
  --sidebar-w: var(--sidebar-expanded);
}

.layout.mobile {
  --sidebar-w: 0px;
  min-height: 100vh;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  width: var(--sidebar-w);
  flex: 0 0 var(--sidebar-w);
  background: #f5f7ff;
  border-right: 1px solid var(--app-border);
  box-shadow: 4px 0 22px rgba(75, 140, 255, 0.08);
  padding: calc(22px + env(safe-area-inset-top)) 12px calc(22px + env(safe-area-inset-bottom));
  box-sizing: border-box;
  overflow: hidden;
  transition: width 0.25s ease, box-shadow 0.2s ease;
  z-index: 20;
}

.sidebar.expanded {
  box-shadow: 10px 0 32px rgba(75, 140, 255, 0.12);
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
  flex-shrink: 0;
}

.brand-name {
  font-weight: 800;
  font-size: 18px;
  color: var(--text-main);
}

.brand-desc {
  color: var(--text-muted);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  min-height: 44px;
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

.menu-label {
  white-space: nowrap;
}

.sidebar:not(.expanded) .brand-text,
.sidebar:not(.expanded) .menu-label {
  opacity: 0;
  pointer-events: none;
  width: 0;
  max-width: 0;
  overflow: hidden;
  transition: opacity 0.15s ease;
}

.sidebar.expanded .brand-text,
.sidebar.expanded .menu-label {
  opacity: 1;
  width: auto;
  max-width: 100%;
}

.content {
  flex: 1;
  min-height: 100vh;
  min-width: 0;
  width: auto;
  background: #f4f7fb;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.content-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 18px 22px 28px;
  box-sizing: border-box;
  width: 100%;
}

.layout.collapsed .content-inner {
  max-width: none;
  margin: 0;
}

.sidebar-toggle {
  position: absolute;
  right: 12px;
  bottom: 16px;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: #fff;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.sidebar-toggle:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.12);
}

.mobile-topbar {
  display: none;
}

.mobile-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mobile-topbar .brand-logo {
  width: 40px;
  height: 40px;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.2);
}

.mobile-topbar .brand-name {
  font-size: 16px;
}

.mobile-topbar .brand-desc {
  font-size: 12px;
}

.menu-button {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  border: 1px solid var(--app-border);
  background: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
  cursor: pointer;
}

.topbar-spacer {
  width: 44px;
  height: 44px;
}

.drawer-body {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 12px calc(16px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, #f8fbff, #eef3fb);
}

:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
}

@media (max-width: 900px) {
  .content-inner {
    padding: 16px;
  }
}

@media (max-width: 768px) {
  .sidebar-toggle {
    display: none;
  }

  .content-inner {
    padding: 16px 14px calc(22px + env(safe-area-inset-bottom));
  }

  .mobile-topbar {
    position: sticky;
    top: 0;
    z-index: 18;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: calc(12px + env(safe-area-inset-top)) 14px 12px;
    background: #f7f9fc;
    border-bottom: 1px solid var(--app-border);
    box-shadow: 0 10px 24px rgba(75, 140, 255, 0.08);
  }
}
</style>
