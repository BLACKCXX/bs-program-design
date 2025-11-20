<script setup>
// ===== 页面逻辑：仅前端态，不依赖后端 =====
import { ref, reactive, computed, watchEffect, onMounted } from 'vue'
import UploadDialog from '../components/UploadDialog.vue'
import { ElMessage } from 'element-plus'
import { Search, Upload } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../api/http' // 预留：将来可从 /api/tags 获取真实标签

const store = useAuthStore()

// —— 顶部控件 —— //
const bulkMode = ref(false)

// —— 左侧筛选状态（仅本地过滤，不发后端） —— //
const filters = reactive({
  tags: [],           // 选中的标签
  dateRange: [],      // [开始, 结束]
  sizeMB: [0, 100],   // 0~100 MB
  devices: [],        // 设备（占位：手机/相机/平板）
})

// —— 数据源（演示数据开关）—— //
// 说明：现在用 DEMO 数据；上线后只要换成接口数据即可；标签会自动跟着数据变化
const USE_DEMO = true
const demoItems = [
  { id: 1, title: '壮丽山景', tags: ['风景','自然'], date: '2024-11-05', sizeMB: 3.2, device: '相机', cover: 'https://picsum.photos/seed/land1/1280/720' },
  { id: 2, title: '现代建筑', tags: ['建筑','城市'], date: '2024-11-04', sizeMB: 2.8, device: '相机', cover: 'https://picsum.photos/seed/build1/1280/720' },
  { id: 3, title: '美味佳肴', tags: ['美食'],      date: '2024-11-03', sizeMB: 1.9, device: '手机', cover: 'https://picsum.photos/seed/food1/1280/720' },
  { id: 4, title: '抽象艺术', tags: ['艺术'],      date: '2024-11-02', sizeMB: 4.1, device: '平板', cover: 'https://picsum.photos/seed/art1/1280/720' },
  { id: 5, title: '野生动物', tags: ['动物','自然'], date: '2024-10-31', sizeMB: 3.7, device: '相机', cover: 'https://picsum.photos/seed/animal1/1280/720' },
  { id: 6, title: '城市夜景', tags: ['建筑','科技'], date: '2024-10-29', sizeMB: 3.5, device: '手机', cover: 'https://picsum.photos/seed/city1/1280/720' },
]
const items = ref(USE_DEMO ? demoItems : [])   // ← 以后换成接口返回即可：items.value = (await api.get('/api/images')).data

// —— 关键点：标签是“动态”的 —— //
// 1) 默认：从 items 自动聚合得出所有标签（去重、排序）
// 2) 将来接后端时：把 ENABLE_REMOTE_TAGS=true，并实现 fetchTags() 从 /api/tags 拉取
const ENABLE_REMOTE_TAGS = false
const allTags = ref([])
async function fetchTags() {
  if (!ENABLE_REMOTE_TAGS) return
  try {
    const { data } = await api.get('/api/tags') // 预期返回形如：['风景','人物',...]
    allTags.value = Array.isArray(data) ? data : []
  } catch {
    // 后端未就绪时静默忽略，保持自动聚合策略
  }
}

// 根据 items 自动推导标签（演示阶段）
watchEffect(() => {
  if (ENABLE_REMOTE_TAGS) return
  const set = new Set()
  for (const it of items.value) (it.tags || []).forEach(t => set.add(String(t)))
  allTags.value = Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
})

// 过滤后的展示列表（仅前端过滤）
const displayItems = computed(() => {
  let arr = [...items.value]
  // 标签
  if (filters.tags.length) {
    arr = arr.filter(it => it.tags?.some(t => filters.tags.includes(t)))
  }
  // 时间
  if (filters.dateRange?.length === 2) {
    const [s, e] = filters.dateRange
    const sd = new Date(s), ed = new Date(e)
    arr = arr.filter(it => {
      const d = new Date(it.date)
      return !isNaN(+d) && d >= sd && d <= ed
    })
  }
  // 大小
  arr = arr.filter(it => {
    const mb = Number(it.sizeMB || 0)
    return mb >= filters.sizeMB[0] && mb <= filters.sizeMB[1]
  })
  // 设备（演示）
  if (filters.devices.length) {
    arr = arr.filter(it => filters.devices.includes(it.device))
  }
  return arr
})

import { useRouter } from 'vue-router'
const router = useRouter()
const onLogout = () => {
  store.logout()
  router.replace('/auth')
}

const resetFilters = () => {
  filters.tags = []
  filters.dateRange = []
  filters.sizeMB = [0, 100]
  filters.devices = []
}

const showUpload = ref(false)
const onUploadClick = () => (showUpload.value = true)

// 接收上传成功事件：演示模式下把新图片临时插入到最前（刷新后会消失，等接后端就改为拉取接口）
const onUploaded = (payload) => {
  if (!payload?.files?.length) return
  if (USE_DEMO) {
    const today = new Date().toISOString().slice(0, 10)
    payload.files.forEach((f, i) => {
      items.value.unshift({
        id: Date.now() + i,
        title: payload.form.title || f.name,
        tags: payload.form.tags || [],
        date: today,
        sizeMB: Math.max(0.1, (f.size/1024/1024)).toFixed(1) * 1,
        cover: f.url, // 仅本地预览URL
      })
    })
  }
  showUpload.value = false
}
onMounted(fetchTags)
</script>

<template>
  <div class="page">
    <!-- 顶部导航 -->
    <header class="nav">
      <div class="left">
        <div class="logo">
          <div class="logo-icon"><span class="dot"></span><span class="tri"></span></div>
          <span class="logo-text">图片管理网站</span>
        </div>
        <el-input class="search" placeholder="搜索图片、标签…" :prefix-icon="Search" clearable />
      </div>
      <div class="right">
        <div class="bulk"><span>批量模式</span><el-switch v-model="bulkMode" /></div>
        <el-button type="primary" :icon="Upload" @click="onUploadClick">上传图片</el-button>
        <el-dropdown trigger="click">
            <span class="el-dropdown-link">
                <el-avatar class="avatar" :size="36" :src="store?.user?.avatar_url || ''">
                {{ (store?.user?.username || 'U').slice(0,1).toUpperCase() }}
                </el-avatar>
            </span>
            <template #dropdown>
                <el-dropdown-menu>
                <el-dropdown-item divided @click="onLogout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
            </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主体：左侧筛选 + 右侧网格 -->
    <section class="content">
      <!-- 左侧筛选 -->
      <aside class="aside">
        <div class="aside-header">
          <h3>筛选</h3>
          <a class="reset" href="javascript:;" @click="resetFilters">重置</a>
        </div>

        <div class="block">
          <div class="block-title">标签</div>
          <el-checkbox-group v-model="filters.tags" class="v-list">
            <template v-if="allTags.length">
              <el-checkbox v-for="t in allTags" :key="t" :label="t" />
            </template>
            <template v-else>
              <div class="empty-help">暂无标签（无数据或未加载）</div>
            </template>
          </el-checkbox-group>
        </div>

        <div class="block">
          <div class="block-title">时间范围</div>
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            range-separator="至"
            unlink-panels
            style="width:100%;"
          />
        </div>

        <div class="block">
          <div class="block-title">文件大小 (0MB - 100MB)</div>
          <el-slider v-model="filters.sizeMB" range :min="0" :max="100" />
        </div>

        <div class="block">
          <div class="block-title">拍摄设备</div>
          <el-checkbox-group v-model="filters.devices" class="v-list">
            <el-checkbox label="手机" /><el-checkbox label="相机" /><el-checkbox label="平板" />
          </el-checkbox-group>
        </div>
      </aside>

      <!-- 右侧卡片网格 -->
      <main class="main">
        <div v-if="!displayItems.length" class="empty">
          <el-empty description="暂无图片，试试右上角“上传图片”" />
        </div>
        <div v-else class="grid">
          <div v-for="it in displayItems" :key="it.id" class="card">
            <div class="cover" :style="it.cover ? { backgroundImage: `url(${it.cover})` } : {}"></div>
            <div class="card-body">
              <h4 class="title">{{ it.title || '未命名' }}</h4>
              <div class="tags">
                <el-tag v-for="t in it.tags" :key="t" size="small" effect="plain">{{ t }}</el-tag>
              </div>
              <div class="meta">
                <span>{{ it.date || '—' }}</span><span>·</span>
                <span>{{ it.sizeMB ? `${it.sizeMB} MB` : '—' }}</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </section>
    <!-- 上传弹窗：标签选项与左侧筛选一致 -->
    <UploadDialog v-model="showUpload": tag-options="allTags" @uploaded="onUploaded"/>

  </div>
</template>

<style scoped>
/* 背景与整体 */
.page { min-height: 100vh; background: #f6f8fb; }

/* 顶部导航 */
.nav {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  height: 64px; padding: 0 18px; background: #fff; border-bottom: 1px solid #eef0f3;
}
.nav .left { display: flex; align-items: center; gap: 16px; flex: 1; min-width: 0; }
.logo { display: flex; align-items: center; gap: 10px; min-width: 180px; }
.logo-icon { width: 34px; height: 34px; border-radius: 10px; background: #eaf2ff; position: relative;
  display:grid; place-items:center; box-shadow: inset 0 6px 16px rgba(59,130,246,.12); }
.logo-icon .dot { width: 6px; height: 6px; background:#2563eb; border-radius:50%; position:absolute; left:8px; top:8px; }
.logo-icon .tri { width:0;height:0;border-left:9px solid transparent;border-right:9px solid transparent;border-bottom:14px solid #2563eb; }
.logo-text { font-weight: 700; color:#28303f; white-space: nowrap; }
.search { max-width: 560px; width: 100%; }
.nav .right { display:flex; align-items:center; gap: 14px; }
.bulk { display:flex; align-items:center; gap: 8px; color:#4b5563; font-size: 14px; }
.avatar { cursor: pointer; }

/* 主体两栏 */
.content { display: grid; grid-template-columns: 260px 1fr; gap: 16px; padding: 16px; }
.aside {
  background:#fff; border:1px solid #eef0f3; border-radius: 12px; padding: 14px;
  height: calc(100vh - 96px); position: sticky; top: 80px; overflow: auto;
}
.aside-header { display:flex; justify-content: space-between; align-items:center; margin-bottom: 6px; }
.aside-header h3 { margin:0; font-size: 16px; }
.reset { font-size: 13px; color:#2563eb; text-decoration: none; }
.block { margin-top: 14px; }
.block-title { font-weight: 600; margin-bottom: 8px; color:#374151; }
.v-list :deep(.el-checkbox) { display:block; margin: 6px 0; }
.empty-help { font-size: 13px; color:#9aa0a6; }

/* 右侧网格与卡片 */
.main { padding-right: 6px; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (min-width: 1400px) { .grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 1100px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px)  { .content { grid-template-columns: 1fr; } .aside { position:static; height:auto; } .grid { grid-template-columns: 1fr; } }

.card { background:#fff; border:1px solid #eef0f3; border-radius: 14px; overflow:hidden;
  transition: transform .15s ease, box-shadow .15s ease; }
.card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(27, 49, 88, 0.12); }
.cover { width:100%; aspect-ratio: 16/9; background: linear-gradient(135deg,#f0f4ff,#ecfeff);
  background-size: cover; background-position: center; }
.card-body { padding: 12px 14px 14px; }
.title { margin: 0 0 6px; font-size: 16px; color:#1f2937; }
.tags { display:flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.meta { font-size: 13px; color:#9aa0a6; display:flex; gap:8px; align-items:center; }
.empty { margin-top: 8vh; }
</style>
