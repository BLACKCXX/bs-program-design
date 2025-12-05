<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Calendar, Picture } from '@element-plus/icons-vue'
import api from '../api/http'

const API = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')
const toAbs = (p) => {
  if (!p) return ''
  return p.startsWith('http') ? p : `${API}${p}`
}

const layoutMode = ref('grid')

const filters = reactive({
  keyword: '',
  dateRange: [],
  dateStart: '',
  dateEnd: '',
  format: '',
  cameraMake: '',
  cameraModel: '',
  iso: '',
  focalLength: '',
  minSizeMB: 0,
  maxSizeMB: 200,
  tags: [],
})

const quickRanges = ['今天', '最近三天', '最近一周', '最近一月']
const activeQuick = ref('')

const loading = ref(false)
const results = ref([])

const loadingTags = ref(false)
const tagOptions = ref([])

const sizeRange = computed({
  get: () => [filters.minSizeMB, filters.maxSizeMB],
  set: (val = []) => {
    filters.minSizeMB = Number(val?.[0] ?? 0)
    filters.maxSizeMB = Number(val?.[1] ?? 200)
  },
})

const resultCount = computed(() => results.value.length)

function formatDateInput(val) {
  if (!val) return ''
  const d = typeof val === 'string' ? new Date(val) : val
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString().slice(0, 10)
}

watch(
  () => filters.dateRange,
  (val) => {
    if (Array.isArray(val) && val.length === 2 && val[0] && val[1]) {
      filters.dateStart = formatDateInput(val[0])
      filters.dateEnd = formatDateInput(val[1])
    } else {
      filters.dateStart = ''
      filters.dateEnd = ''
      activeQuick.value = ''
    }
  },
  { deep: true }
)

// 高级筛选变更后自动触发搜索（防抖）
let debounceTimer
const scheduleLoad = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadSearchResults(), 400)
}
const cancelScheduledLoad = () => clearTimeout(debounceTimer)

watch(
  () => ({
    dateStart: filters.dateStart,
    dateEnd: filters.dateEnd,
    format: filters.format,
    cameraMake: filters.cameraMake,
    cameraModel: filters.cameraModel,
    iso: filters.iso,
    focalLength: filters.focalLength,
    minSizeMB: filters.minSizeMB,
    maxSizeMB: filters.maxSizeMB,
    tags: [...filters.tags],
  }),
  () => scheduleLoad(),
  { deep: true }
)

const mapResult = (item) => ({
  id: item.id,
  title: item.title,
  description: item.description,
  tags: item.tags || [],
  date: item.date,
  size: item.sizeMB != null ? `${item.sizeMB} MB` : '',
  cover: toAbs(item.url || ''),
})

const loadSearchResults = async () => {
  loading.value = true
  try {
    const params = { limit: 50, offset: 0 }
    const keyword = filters.keyword.trim()
    if (keyword) params.q = keyword
    if (filters.dateStart) params.date_start = filters.dateStart
    if (filters.dateEnd) params.date_end = filters.dateEnd
    if (filters.format) params.format = filters.format.trim()

    const cameraMake = filters.cameraMake.trim()
    const cameraModel = filters.cameraModel.trim()
    const iso = filters.iso.toString().trim()
    const focal = filters.focalLength.toString().trim()
    if (cameraMake) params.camera_make = cameraMake
    if (cameraModel) params.camera_model = cameraModel
    if (iso) params.iso = iso
    if (focal) params.focal_length = focal
    const sizeTouched = filters.minSizeMB > 0 || filters.maxSizeMB < 200
    if (sizeTouched) {
      params.min_size_mb = filters.minSizeMB
      params.max_size_mb = filters.maxSizeMB
    }
    if (filters.tags.length) params.tags = filters.tags

    const { data } = await api.get('/api/images/search', { params })
    results.value = (data.items || []).map(mapResult)
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '搜索失败')
  } finally {
    loading.value = false
  }
}

const loadTagOptions = async (keyword = '') => {
  loadingTags.value = true
  try {
    const { data } = await api.get('/api/tags', { params: { q: keyword || undefined } })
    tagOptions.value = (Array.isArray(data) ? data : []).map((name) => ({ name }))
  } catch (err) {
    console.error(err)
  } finally {
    loadingTags.value = false
  }
}

const onSearch = () => {
  loadSearchResults()
}

const onReset = () => {
  filters.keyword = ''
  filters.dateRange = []
  filters.dateStart = ''
  filters.dateEnd = ''
  filters.format = ''
  filters.cameraMake = ''
  filters.cameraModel = ''
  filters.iso = ''
  filters.focalLength = ''
  filters.minSizeMB = 0
  filters.maxSizeMB = 200
  filters.tags = []
  activeQuick.value = ''
  cancelScheduledLoad()
  loadSearchResults()
}

const applyQuick = (label) => {
  const end = new Date()
  let start = new Date()
  if (label === '今天') {
    start = new Date()
  } else if (label === '最近三天') {
    start.setDate(end.getDate() - 2)
  } else if (label === '最近一周') {
    start.setDate(end.getDate() - 6)
  } else if (label === '最近一月') {
    start.setDate(end.getDate() - 29)
  }
  filters.dateRange = [start, end]
  activeQuick.value = label
}

onMounted(() => {
  loadTagOptions()
  loadSearchResults()
})
</script>

<template>
  <div class="search-page">
    <div class="header">
      <div>
        <h2>搜索引擎 · 全局检索</h2>
        <p class="sub">名称/标签/EXIF/时间/文件属性多维组合筛选，快速命中想要的图片</p>
      </div>
    </div>

    <div class="search-bar card">
      <el-input
        v-model="filters.keyword"
        size="large"
        placeholder="输入图片名称、文件名或关键词（回车搜索）"
        :prefix-icon="Search"
        @keyup.enter="onSearch"
      />
      <div class="search-actions">
        <el-button type="primary" :icon="Search" size="large" @click="onSearch">搜索</el-button>
        <el-button :icon="Refresh" size="large" @click="onReset">清空条件</el-button>
      </div>
    </div>

    <div class="card filter-card">
      <div class="card-title">
        <span>高级筛选</span>
        <span class="count">当前结果：{{ resultCount }} 条</span>
      </div>

      <div class="filter-grid">
        <el-form label-position="top">
          <div class="row">
            <el-form-item label="拍摄/上传时间">
              <el-date-picker
                v-model="filters.dateRange"
                type="daterange"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                unlink-panels
                :prefix-icon="Calendar"
                style="width: 100%;"
              />
              <div class="quick-range">
                <el-check-tag
                  v-for="tag in quickRanges"
                  :key="tag"
                  :checked="activeQuick === tag"
                  @click="applyQuick(tag)"
                >
                  {{ tag }}
                </el-check-tag>
              </div>
            </el-form-item>

            <el-form-item label="图片格式">
              <el-select v-model="filters.format" placeholder="选择需要的文件格式" clearable>
                <el-option label="JPG" value="jpg" />
                <el-option label="PNG" value="png" />
                <el-option label="WEBP" value="webp" />
                <el-option label="HEIC" value="heic" />
              </el-select>
            </el-form-item>
          </div>

          <div class="row">
            <el-form-item label="EXIF 维度">
              <div class="exif-grid">
                <el-input v-model="filters.cameraMake" placeholder="相机品牌" clearable />
                <el-input v-model="filters.cameraModel" placeholder="相机型号" clearable />
                <el-input v-model="filters.iso" placeholder="ISO (如 100)" clearable />
                <el-input v-model="filters.focalLength" placeholder="焦距 (如 35)" clearable />
              </div>
            </el-form-item>
          </div>

          <div class="row">
            <el-form-item label="文件大小 (MB)">
              <el-slider v-model="sizeRange" :max="200" range :show-tooltip="true" />
              <div class="size-meta">{{ filters.minSizeMB }} - {{ filters.maxSizeMB }} MB</div>
            </el-form-item>
          </div>

          <div class="row">
            <el-form-item label="标签筛选">
              <el-select
                v-model="filters.tags"
                multiple
                filterable
                remote
                :remote-method="loadTagOptions"
                :loading="loadingTags"
                collapse-tags
                placeholder="按标签筛选（可多选）"
              >
                <el-option
                  v-for="tag in tagOptions"
                  :key="tag.name"
                  :label="tag.name"
                  :value="tag.name"
                />
              </el-select>
            </el-form-item>
          </div>
        </el-form>
      </div>
    </div>

    <div class="card layout-switcher">
      <div class="layout-left">
        <span class="label">布局切换</span>
        <span class="muted">同一批数据，多种展示方式</span>
      </div>
      <el-button-group class="layout-buttons">
        <el-button :type="layoutMode === 'grid' ? 'primary' : 'default'" @click="layoutMode = 'grid'">网格</el-button>
        <el-button :type="layoutMode === 'card' ? 'primary' : 'default'" @click="layoutMode = 'card'">大卡片</el-button>
        <el-button :type="layoutMode === 'masonry' ? 'primary' : 'default'" @click="layoutMode = 'masonry'">瀑布流</el-button>
      </el-button-group>
    </div>

    <div class="card result-card">
      <div class="card-title space">
        <div class="title-left">
          <el-icon><Picture /></el-icon>
          <span>搜索结果</span>
        </div>
        <div class="tag-row">
          <el-tag type="info" effect="plain">{{ resultCount }} 条</el-tag>
          <el-tag v-if="filters.tags.length" type="success" effect="plain">标签: {{ filters.tags.join('、') }}</el-tag>
        </div>
      </div>

      <div v-if="loading" class="loading">正在检索…</div>
      <div v-else-if="!results.length" class="empty">
        <el-empty description="暂无匹配结果" />
      </div>
      <template v-else>
        <div v-if="layoutMode === 'grid'" class="search-result search-result--grid">
          <div v-for="item in results" :key="item.id" class="result-item">
            <div class="thumb" :style="{ backgroundImage: `url(${item.cover})` }"></div>
            <div class="info">
              <div class="title">{{ item.title }}</div>
              <div class="meta">{{ item.date || '未知时间' }} · {{ item.size || '未知大小' }}</div>
              <div class="tags">
                <el-tag v-for="tag in item.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-else-if="layoutMode === 'card'" class="search-result search-result--card">
          <div v-for="item in results" :key="item.id" class="wide-card">
            <div class="card-cover" :style="{ backgroundImage: `url(${item.cover})` }"></div>
            <div class="card-info">
              <div class="title-row">
                <div class="title">{{ item.title }}</div>
                <span class="meta">{{ item.date || '未知时间' }} · {{ item.size || '未知大小' }}</span>
              </div>
              <p v-if="item.description" class="desc">{{ item.description }}</p>
              <div class="tags">
                <el-tag v-for="tag in item.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="search-result search-result--masonry">
          <div v-for="item in results" :key="item.id" class="masonry-item">
            <div class="masonry-cover" :style="{ backgroundImage: `url(${item.cover})` }"></div>
            <div class="info">
              <div class="title">{{ item.title }}</div>
              <div class="meta">{{ item.date || '未知时间' }} · {{ item.size || '未知大小' }}</div>
              <div class="tags">
                <el-tag v-for="tag in item.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.search-page {
  --primary: var(--app-primary);
  --primary-strong: var(--app-primary-strong);
  --soft: var(--app-primary-soft);
  --accent: var(--app-accent);
  --border: var(--app-border);
  --text: var(--app-text);
  --muted: var(--app-muted);
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
}

.header h2 {
  margin: 0;
  color: var(--primary-strong);
}

.sub {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 14px;
}

.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 12px 26px rgba(75, 140, 255, 0.08);
}

.search-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-actions {
  display: flex;
  gap: 10px;
}

.filter-card .card-title,
.result-card .card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 700;
  color: var(--primary-strong);
}

.count {
  color: var(--muted);
  font-size: 13px;
}

.filter-grid {
  background: #f8fbff;
  border: 1px dashed var(--border);
  border-radius: 14px;
  padding: 12px;
}

.row {
  display: flex;
  flex-direction: column;
}

.row + .row {
  margin-top: 12px;
}

.quick-range {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.exif-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.size-meta {
  margin-top: 6px;
  font-size: 13px;
  color: var(--muted);
}

.layout-switcher {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.layout-left .label {
  font-weight: 700;
  color: var(--primary-strong);
}

.layout-left .muted {
  color: var(--muted);
  font-size: 13px;
}

.layout-buttons :deep(.el-button) {
  min-width: 94px;
}

.result-card .space {
  margin-bottom: 10px;
}

.title-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-row {
  display: flex;
  gap: 8px;
}

.loading {
  padding: 22px 8px;
  color: var(--muted);
}

.search-result--grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.result-item,
.masonry-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
}

.thumb,
.masonry-cover {
  background-size: cover;
  background-position: center;
  aspect-ratio: 4 / 3;
}

.info {
  padding: 10px 12px 12px;
}

.title {
  font-weight: 700;
  color: var(--text);
}

.meta {
  color: var(--muted);
  font-size: 13px;
  margin: 4px 0;
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.search-result--card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wide-card {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
}

.card-cover {
  background-size: cover;
  background-position: center;
  min-height: 180px;
}

.card-info {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.title-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
}

.desc {
  margin: 0;
  color: var(--text);
  line-height: 1.5;
}

.search-result--masonry {
  column-count: 3;
  column-gap: 14px;
}

.masonry-item {
  break-inside: avoid;
  margin-bottom: 14px;
}

@media (max-width: 960px) {
  .search-bar {
    flex-direction: column;
  }

  .search-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .exif-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .wide-card {
    grid-template-columns: 1fr;
  }

  .search-result--masonry {
    column-count: 2;
  }
}

@media (max-width: 640px) {
  .exif-grid {
    grid-template-columns: 1fr;
  }

  .search-result--grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  }

  .search-result--masonry {
    column-count: 1;
  }
}
</style>
