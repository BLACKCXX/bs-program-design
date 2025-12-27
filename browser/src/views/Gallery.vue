



<script setup>

// ===== 页面逻辑：仅前端态，不依赖后端 =====
import { ref, reactive, computed, onMounted, watch } from 'vue'
import UploadDialog from '../components/UploadDialog.vue'
import DateRangeInput from '../components/DateRangeInput.vue'
import { ElMessage } from 'element-plus'
import { Search, Upload, Download, Delete, PriceTag } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../api/http' // 预留：将来可从 /api/tags 获取真实标签
import { toDisplayUrl } from '../utils/url'
//import api from '../api/http'
const store = useAuthStore()
const toAbs = (p) => toDisplayUrl(p)
// —— 顶部控件 —— //
const bulkMode = ref(false)
const selectedIds = ref([]) // #advise 批量模式选中列表

// —— 左侧筛选状态（仅本地过滤，不发后端） —— //
const filters = reactive({
  keyword: '',        // #advise 顶部搜索关键字
  tags: [],           // 选中的标签
  dateStart: '',      // 开始日期
  dateEnd: '',        // 结束日期
  sizeMB: [0, 10],   // 0~10 MB
  devices: [],        // 设备（占位：手机/相机/平板）
})
const tagKeyword = ref('')       // #advise 标签搜索关键字（标签+图片标题模糊）
const popularTags = ref([])      // #advise 左侧显示的热门标签（仅前5）
const uploadTagOptions = computed(() => popularTags.value.map((t) => t.name))
const facets = reactive({ device: [], camera_make: [], camera_model: [], format: [] })
const facetLoaded = ref(false)

// —— 数据源（演示数据开关）—— //
// 说明：现在用 DEMO 数据；上线后只要换成接口数据即可；标签会自动跟着数据变化
//const USE_DEMO = true
//const demoItems = [
//  { id: 1, title: '壮丽山景', tags: ['风景','自然'], date: '2024-11-05', sizeMB: 3.2, device: '相机', cover: 'https://picsum.photos/seed/land1/1280/720' },
 // { id: 2, title: '现代建筑', tags: ['建筑','城市'], date: '2024-11-04', sizeMB: 2.8, device: '相机', cover: 'https://picsum.photos/seed/build1/1280/720' },
//  { id: 3, title: '美味佳肴', tags: ['美食'],      date: '2024-11-03', sizeMB: 1.9, device: '手机', cover: 'https://picsum.photos/seed/food1/1280/720' },
//  { id: 4, title: '抽象艺术', tags: ['艺术'],      date: '2024-11-02', sizeMB: 4.1, device: '平板', cover: 'https://picsum.photos/seed/art1/1280/720' },
 // { id: 5, title: '野生动物', tags: ['动物','自然'], date: '2024-10-31', sizeMB: 3.7, device: '相机', cover: 'https://picsum.photos/seed/animal1/1280/720' },
 // { id: 6, title: '城市夜景', tags: ['建筑','科技'], date: '2024-10-29', sizeMB: 3.5, device: '手机', cover: 'https://picsum.photos/seed/city1/1280/720' },
//]
//const items = ref(USE_DEMO ? demoItems : [])   // ← 以后换成接口返回即可：items.value = (await api.get('/api/images')).data

// —— 关键点：标签是“动态”的 —— //
// 1) 默认：从 items 自动聚合得出所有标签（去重、排序）
// 2) 将来接后端时：把 ENABLE_REMOTE_TAGS=true，并实现 fetchTags() 从 /api/tags 拉取

const USE_DEMO = false
const items = ref([])
const loadingList = ref(false) // #advise 列表加载态
const tagOptions = ref([])
const tagLoading = ref(false)

const formatDate = (val) => {
  if (!val) return ''
  if (typeof val === 'string') return val.slice(0, 10)
  const d = new Date(val)
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10)
}

const buildParams = () => {
  const params = { limit: 200, offset: 0 }
  const kw = (filters.keyword || '').trim()
  if (kw) params.q = kw
  if (filters.tags.length) params.tags = filters.tags
  const ds = formatDate(filters.dateStart)
  const de = formatDate(filters.dateEnd)
  if (ds) params.date_start = ds
  if (de) params.date_end = de
  params.min_size_mb = Math.max(0, Number(filters.sizeMB?.[0] ?? 0))
  params.max_size_mb = Math.min(10, Number(filters.sizeMB?.[1] ?? 10))
  return params
}

const loadImages = async () => {
  loadingList.value = true
  try {
    const { data } = await api.get('/api/images/search', { params: buildParams() })
    items.value = (data.items || []).map((it) => ({
      id: it.id,
      title: it.title,
      tags: it.tags,
      date: it.date,
      sizeMB: it.sizeMB,
      device: it.device || '',
      cover: toAbs(it.url),
      description: it.description,
    }))
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || 'Load images failed')
  } finally {
    loadingList.value = false
  }
}

const fetchPopularTags = async () => {
  try {
    const { data } = await api.get('/api/tags/popular', { params: { q: tagKeyword.value || undefined } })
    const sorted = (data || []).sort((a, b) => (b.image_count - a.image_count) || a.name.localeCompare(b.name, 'zh-Hans-CN'))
    popularTags.value = sorted.slice(0, 5)
  } catch (err) {
    console.error(err)
  }
}

const loadFacets = async () => {
  if (facetLoaded.value) return
  try {
    const { data } = await api.get('/api/images/facets')
    facets.device = data?.device || []
    facets.camera_make = data?.camera_make || []
    facets.camera_model = data?.camera_model || []
    facets.format = data?.format || []
    facetLoaded.value = true
  } catch (err) {
    ElMessage.warning(err?.response?.data?.error || '获取筛选建议失败')
  }
}

const onTagSearchInput = () => {
  clearTimeout(onTagSearchInput.timer)
  onTagSearchInput.timer = setTimeout(fetchPopularTags, 300)
}

const loadTagOptions = async (kw = '') => {
  tagLoading.value = true
  try {
    const { data } = await api.get('/api/tags', { params: { q: kw || undefined } })
    const list = Array.isArray(data) ? data : []
    const base = list.map((t) => ({ label: t, value: t }))
    const trimmed = (kw || '').trim()
    // #advise 批量添加标签时，允许创建不存在的标签
    if (trimmed && !list.includes(trimmed)) {
      base.unshift({ label: `创建新标签：${trimmed}`, value: trimmed, isNew: true })
    }
    tagOptions.value = base
  } catch (err) {
    console.error(err)
  } finally {
    tagLoading.value = false
  }
}

// 过滤后的展示列表（仅本地后处理：设备筛选）
const displayItems = computed(() => {
  let arr = [...items.value]
  if (filters.devices.length) {
    arr = arr.filter((it) => filters.devices.includes(it.device))
  }
  return arr
})

import { useRouter } from 'vue-router'
const router = useRouter()
const onLogout = () => {
  store.logout()
  router.replace('/auth')
}
// 新增：点击卡片跳转到详情页（先走本地路由，后续可接真实数据）
const goDetail = (id) => router.push({ name: 'ImageDetail', params: { id } })

// #advise 批量模式：选中、工具条与退出
const selectedCount = computed(() => selectedIds.value.length)
const toggleSelect = (id) => {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}
const onCardClick = (id) => {
  if (bulkMode.value) {
    toggleSelect(id)
  } else {
    goDetail(id)
  }
}
watch(bulkMode, (val) => {
  if (!val) selectedIds.value = []
})

const downloadSelected = async () => {
  if (!selectedIds.value.length) return
  try {
    const { data } = await api.post(
      '/api/images/batch/download',
      { image_ids: selectedIds.value },
      { responseType: 'blob' }
    )
    const url = window.URL.createObjectURL(new Blob([data]))
    const a = document.createElement('a')
    a.href = url
    a.download = 'private-picture-shop.zip'
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '批量下载失败')
  }
}

const deleteSelected = async () => {
  if (!selectedIds.value.length) return
  try {
    await api.post('/api/images/batch/delete', { image_ids: selectedIds.value })
    ElMessage.success('已删除选中图片')
    selectedIds.value = []
    await loadImages()
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '删除失败')
  }
}

const showTagDialog = ref(false)
const dialogTags = ref([])
const openAddTagDialog = () => {
  if (!selectedIds.value.length) {
    ElMessage.warning('请先选择图片')
    return
  }
  dialogTags.value = []
  loadTagOptions()
  showTagDialog.value = true
}
const confirmAddTags = async () => {
  if (!dialogTags.value.length || !selectedIds.value.length) {
    showTagDialog.value = false
    return
  }
  try {
    await api.post('/api/images/batch/add_tags', { image_ids: selectedIds.value, tags: dialogTags.value })
    ElMessage.success('已添加标签')
    showTagDialog.value = false
    await loadImages()
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '添加标签失败')
  }
}

let filterTimer
watch(
  () => ({ ...filters, tags: [...filters.tags], sizeMB: [...filters.sizeMB] }),
  () => {
    clearTimeout(filterTimer)
    filterTimer = setTimeout(loadImages, 400)
  },
  { deep: true }
)

onMounted(() => {
  fetchPopularTags()
  loadFacets()
  loadImages()
})

const resetFilters = () => {
  filters.keyword = ''
  filters.tags = []
  filters.dateStart = ''
  filters.dateEnd = ''
  filters.sizeMB = [0, 10]
  filters.devices = []
  loadImages()
}

const showUpload = ref(false)
const onUploadClick = () => (showUpload.value = true)
const onUploaded = async () => { await loadImages() }
// 接收上传成功事件：演示模式下把新图片临时插入到最前（刷新后会消失，等接后端就改为拉取接口）
/*const onUploaded = (payload) => {
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
onMounted(fetchTags)*/


</script>



<template>
  <div class="page">
    <!-- 顶部导航 -->
    <header class="nav">
      <div class="left">
        <div class="logo">
          <div class="logo-badge">P</div>
          <div class="logo-text">
            <div class="logo-title">Private Picture Shop</div>
            <div class="logo-sub">Your Private Image Manager</div>
          </div>
        </div>
        <el-input
          v-model="filters.keyword"
          class="search"
          placeholder="搜索图片、描述或标签…"
          :prefix-icon="Search"
          clearable
          @keyup.enter="loadImages"
        />
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

    <div v-if="bulkMode" class="bulk-bar card">
      <div class="bulk-info">已选择 {{ selectedCount }} 张图片</div>
      <div class="bulk-actions">
        <el-button :icon="Download" :disabled="!selectedCount" @click="downloadSelected">下载</el-button>
        <el-button type="danger" :icon="Delete" :disabled="!selectedCount" @click="deleteSelected">删除</el-button>
        <el-button type="primary" :icon="PriceTag" :disabled="!selectedCount" @click="openAddTagDialog">添加标签</el-button>
      </div>
      <el-button class="exit-bulk" @click="bulkMode = false">退出批量</el-button>
    </div>

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
          <el-input
            v-model="tagKeyword"
            size="small"
            placeholder="搜索标签/标题"
            clearable
            @input="onTagSearchInput"
          />
          <el-checkbox-group v-model="filters.tags" class="v-list">
            <template v-if="popularTags.length">
              <el-checkbox v-for="t in popularTags" :key="t.id" :label="t.name">
                <span class="tag-name">{{ t.name }}</span>
                <span class="tag-count">{{ t.image_count }}</span>
              </el-checkbox>
            </template>
            <template v-else>
              <div class="empty-help">暂无热门标签</div>
            </template>
          </el-checkbox-group>
        </div>

        <div class="block">
          <div class="block-title">时间范围</div>
          <DateRangeInput
            v-model:start="filters.dateStart"
            v-model:end="filters.dateEnd"
            placeholder-start="开始日期"
            placeholder-end="结束日期"
            size="small"
          />
        </div>

        <div class="block">
          <div class="block-title">文件大小 (0MB - 10MB)</div>
          <el-slider v-model="filters.sizeMB" range :min="0" :max="10" />
        </div>

        <div class="block">
          <div class="block-title">拍摄设备</div>
          <el-select
            v-model="filters.devices"
            multiple
            filterable
            clearable
            placeholder="选择设备类型"
            style="width: 100%;"
          >
            <el-option
              v-for="opt in facets.device"
              :key="opt.value"
              :label="`${opt.value}（${opt.count}）`"
              :value="opt.value"
            />
          </el-select>
        </div>
      </aside>

      <!-- 右侧卡片网格 -->
      <main class="main">
        <div v-if="loadingList" class="empty">
          <el-empty description="加载中..." />
        </div>
        <div v-else-if="!displayItems.length" class="empty">
          <el-empty description="暂无图片，试试右上角“上传图片”" />
        </div>
        <div v-else class="grid">
          <!-- 新增：卡片可点击跳转详情页 -->
          <div
            v-for="it in displayItems"
            :key="it.id"
            class="card"
            :class="{ 'is-selectable': bulkMode, 'is-selected': selectedIds.includes(it.id) }"
            @click="onCardClick(it.id)"
          >
            <div v-if="bulkMode" class="card-checkbox">
              <el-checkbox :model-value="selectedIds.includes(it.id)" @change.stop="toggleSelect(it.id)" />
            </div>
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
    <el-dialog v-model="showTagDialog" title="为选中图片添加标签" width="420px">
      <el-select
        v-model="dialogTags"
        multiple
        filterable
        remote
        :remote-method="loadTagOptions"
        :loading="tagLoading"
        allow-create
        default-first-option
        collapse-tags
        :max-collapse-tags="4"
        :reserve-keyword="false"
        placeholder="选择或创建标签"
        style="width: 100%;"
      >
        <el-option v-for="opt in tagOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <template #footer>
        <el-button @click="showTagDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAddTags">确定</el-button>
      </template>
    </el-dialog>
    <!-- 上传弹窗：标签选项与左侧筛选一致 -->
    <UploadDialog v-model="showUpload" :tag-options="uploadTagOptions" @uploaded="onUploaded"/>

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
.logo { display: flex; align-items: center; gap: 10px; min-width: 220px; }
.logo-badge { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center;
  background: linear-gradient(135deg, #e0ecff, #c7dbff); color: #1d4ed8; font-weight: 800; box-shadow: 0 6px 18px rgba(59,130,246,.18); }
.logo-text { display: flex; flex-direction: column; }
.logo-title { font-weight: 800; color:#1f2937; line-height: 1.2; }
.logo-sub { font-size: 12px; color:#6b7280; }
.search { max-width: 560px; width: 100%; }
.nav .right { display:flex; align-items:center; gap: 14px; }
.bulk { display:flex; align-items:center; gap: 8px; color:#4b5563; font-size: 14px; }
.avatar { cursor: pointer; }

.bulk-bar { display: flex; align-items: center; gap: 14px; margin: 8px 18px 0; }
.bulk-info { font-weight: 700; color: #1f2937; }
.bulk-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.exit-bulk { margin-left: auto; }

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
.tag-name { margin-right: 6px; }
.tag-count { color: #6b7280; font-size: 12px; }
.empty-help { font-size: 13px; color:#9aa0a6; }

/* 右侧网格与卡片 */
.main { padding-right: 6px; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (min-width: 1400px) { .grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 1100px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px)  { .content { grid-template-columns: 1fr; } .aside { position:static; height:auto; } .grid { grid-template-columns: 1fr; } }

.card { position: relative; background:#fff; border:1px solid #eef0f3; border-radius: 14px; overflow:hidden;
  transition: transform .15s ease, box-shadow .15s ease; cursor: pointer; /* 新增：提示卡片可点击进入详情 */ }
.card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(27, 49, 88, 0.12); }
.card.is-selectable { border-color: #d6e4ff; }
.card.is-selected { transform: translateY(2px); box-shadow: 0 12px 26px rgba(37, 99, 235, 0.2); border-color: #2563eb; }
.cover { width:100%; aspect-ratio: 16/9; background: linear-gradient(135deg,#f0f4ff,#ecfeff);
  background-size: cover; background-position: center; }
.card-body { padding: 12px 14px 14px; }
.title { margin: 0 0 6px; font-size: 16px; color:#1f2937; }
.tags { display:flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.meta { font-size: 13px; color:#9aa0a6; display:flex; gap:8px; align-items:center; }
.card-checkbox { position: absolute; top: 10px; right: 10px; z-index: 2; background: rgba(255,255,255,0.8); border-radius: 8px; padding: 2px 4px; }
.empty { margin-top: 8vh; }

@media (max-width: 768px) {
  .nav {
    height: auto;
    padding: 10px 12px;
    gap: 10px;
    flex-wrap: wrap;
  }

  .logo {
    min-width: 0;
  }

  .search {
    max-width: 100%;
  }

  .nav .right {
    width: 100%;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }

  .bulk-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .content {
    padding: 12px;
  }

  .grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  }
}
</style>
