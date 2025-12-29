  <script setup>
// 页面职责：加载 /api/images/:id 的详情并展示预览/信息
import { ref, computed, onUnmounted, watch, onMounted, nextTick } from 'vue'
import api from '../api/http'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Download, Delete as DeleteIcon, ZoomOut, ZoomIn, FullScreen, MagicStick } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

// 图片详情的初始结构，避免响应式缺字段
const emptyImage = {
  id: null,
  title: '',
  description: '',
  visibility: 'public',
  url: '',
  width: null,
  height: null,
  sizeMB: null,
  format: '',
  createdAt: '',
  takenAt: '',
  tags: [],
  exif: {},
  relations: { parent: null, children: [] },
}
const image = ref({ ...emptyImage })
const suggestedTags = ref([])
const savingTag = ref(false)
const aiTagLoading = ref(false)
const previewSrc = ref('')
const blobUrl = ref('')
const previewKey = computed(() => `${previewSrc.value || 'empty'}`)
const loading = ref(false)
const loadError = ref('')

// 右侧信息区和预览相关 UI 状态
const activeTab = ref('basic')
const zoom = ref(100)
const fitMode = ref('width')
const showGps = ref(false)
const newTag = ref('')
const tagTypes = ['success', 'warning', 'info', 'danger']

const visibilityOptions = [
  { label: '公开', value: 'public' },
  { label: '私密', value: 'private' },
]

// 文件信息：尺寸与大小展示
const fileInfo = computed(() => ({
  sizeText: image.value.sizeMB ? `${image.value.sizeMB} MB` : '未知',
  dimension: image.value.width && image.value.height ? `${image.value.width} × ${image.value.height}` : '未知',
}))

const onBack = () => router.back()
const changeZoom = (delta) => {
  zoom.value = Math.min(200, Math.max(50, zoom.value + delta))
}
const fitLabel = computed(() => (fitMode.value === 'width' ? '适应屏幕' : '宽度适配'))
const fitScreen = () => {
  fitMode.value = fitMode.value === 'width' ? 'contain' : 'width'
  zoom.value = 100
}
// 顶部动作：下载与删除
const onDownload = () => {
  const raw = (image.value.url || '').split('?')[0]
  if (!raw) {
    ElMessage.warning('暂无可下载文件')
    return
  }
  const a = document.createElement('a')
  a.href = raw
  a.download = image.value.title || `image_${image.value.id || ''}`
  a.click()
}

const onDelete = async () => {
  if (!image.value.id) return
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除吗？', '确认删除', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/images/${image.value.id}`)
    ElMessage.success('删除成功')
    router.replace({ name: 'gallery' })
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '删除失败')
  }
}
const onFieldChange = () => {
  console.log('TODO: 保存元数据到后端', image.value)
}
const removeTag = (tag) => {
  image.value.tags = image.value.tags.filter((t) => t !== tag)
  console.log('TODO: 调用后端删除标签', tag)
}
const addTag = async (tagPayload) => {
  if (!image.value.id) return
  const name = (tagPayload || newTag.value || '').trim()
  if (!name) return
  if (image.value.tags.includes(name)) {
    ElMessage.info('标签已存在')
    newTag.value = ''
    return
  }
  savingTag.value = true
  try {
    const { data } = await api.post(`/api/images/${image.value.id}/tags/accept_suggestions`, { tags: [name] })
    const next = Array.isArray(data?.tags) ? data.tags : Array.from(new Set([...(image.value.tags || []), name]))
    image.value.tags = next
    suggestedTags.value = (suggestedTags.value || []).filter((t) => t !== name)
    ElMessage.success('已添加标签')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '添加标签失败')
  } finally {
    savingTag.value = false
    newTag.value = ''
  }
}
const addAiTags = async () => {
  if (!image.value.id || aiTagLoading.value) return
  aiTagLoading.value = true
  try {
    const { data } = await api.post(`/api/images/${image.value.id}/ai_tags`)
    const incoming = Array.isArray(data?.tags) ? data.tags : []
    if (!incoming.length) {
      ElMessage.info('AI 未返回标签')
      return
    }
    const existing = new Set(image.value.tags || [])
    const toAdd = incoming
      .map((t) => String(t || '').trim())
      .filter((t) => t && !existing.has(t))
    if (!toAdd.length) {
      ElMessage.info('标签已存在')
      return
    }
    const { data: saved } = await api.post(`/api/images/${image.value.id}/tags/accept_suggestions`, { tags: toAdd })
    const next = Array.isArray(saved?.tags)
      ? saved.tags
      : Array.from(new Set([...(image.value.tags || []), ...toAdd]))
    image.value.tags = next
    ElMessage.success('AI 标签已添加')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || 'AI 标签添加失败')
  } finally {
    aiTagLoading.value = false
  }
}
const toggleGps = () => {
  showGps.value = !showGps.value
}

const normalizeFilePath = (p = '') => {
  if (!p) return ''
  let clean = String(p).replace(/\\/g, '/').replace(/^\/+/, '')
  clean = clean.replace(/^files\//, '')
  return `/files/${encodeURI(clean)}`
}

const pickUrl = (data = {}) =>
  data.url ||
  data.cover_url ||
  data.thumb_url ||
  data.stored_path ||
  data.path ||
  data.thumb ||
  ''

const stageRef = ref(null)
const stageSize = ref({ w: 0, h: 0 })
const imgNatural = ref({ w: 0, h: 0 })
let stageObserver = null

const rotateDeg = computed(() => {
  const raw = image.value.rotate ?? image.value.rotation ?? image.value.angle ?? 0
  const val = Number(raw)
  return Number.isFinite(val) ? val : 0
})
const bboxSize = computed(() => {
  const w = imgNatural.value.w
  const h = imgNatural.value.h
  if (!w || !h) return { w: 0, h: 0 }
  const rad = Math.abs((rotateDeg.value * Math.PI) / 180)
  const cos = Math.abs(Math.cos(rad))
  const sin = Math.abs(Math.sin(rad))
  return { w: w * cos + h * sin, h: w * sin + h * cos }
})
const baseScale = computed(() => {
  const w = stageSize.value.w
  const h = stageSize.value.h
  const bw = bboxSize.value.w
  const bh = bboxSize.value.h
  if (!w || !h || !bw || !bh) return 1
  if (fitMode.value === 'contain') {
    return Math.min(w / bw, h / bh) * 0.98
  }
  return w / bw
})
const renderScale = computed(() => baseScale.value * (zoom.value / 100))
const renderBox = computed(() => ({
  w: bboxSize.value.w ? bboxSize.value.w * renderScale.value : 0,
  h: bboxSize.value.h ? bboxSize.value.h * renderScale.value : 0,
}))
const previewHolderStyle = computed(() => {
  if (!renderBox.value.w || !renderBox.value.h) return {}
  return {
    width: `${renderBox.value.w}px`,
    height: `${renderBox.value.h}px`,
  }
})
const previewImgStyle = computed(() => {
  if (!imgNatural.value.w || !imgNatural.value.h) return {}
  return {
    width: `${imgNatural.value.w}px`,
    height: `${imgNatural.value.h}px`,
    transform: `translate(-50%, -50%) rotate(${rotateDeg.value}deg) scale(${renderScale.value})`,
    transformOrigin: 'center center',
  }
})

const fetchPreviewBlob = async (url) => {
  try {
    const resp = await api.get(url, { responseType: 'blob' })
    if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = URL.createObjectURL(resp.data)
    previewSrc.value = blobUrl.value
  } catch (err) {
    console.error('[preview] blob fetch failed', url, err)
    ElMessage.error('图片加载失败')
  }
}

const onImgError = async (e) => {
  const badUrl = e?.target?.src
  console.error('[preview] load error', badUrl)
  if (badUrl && badUrl.startsWith('blob:')) return
  if (image.value.url) {
    await fetchPreviewBlob(image.value.url)
  }
}

const updateStageSize = () => {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) return
  stageSize.value = { w: rect.width, h: rect.height }
}

const onPreviewLoad = async (e) => {
  const el = e.target
  imgNatural.value = { w: el.naturalWidth, h: el.naturalHeight }
  await nextTick()
  updateStageSize()
}

// 加载图片详情，附带版本戳破缓存，填充关系与标签
const loadDetail = async () => {
  try {
    loading.value = true
    loadError.value = ''
    previewSrc.value = ''
    const { data } = await api.get(`/api/images/${route.params.id}`)
    const picked = pickUrl(data)
    const stamp =
      data.updated_at ||
      data.updatedAt ||
      data.updated ||
      data.updatedAt ||
      data.updated_at ||
      data.updated_at ||
      data.created_at ||
      data.createdAt
    const queryBust = Number(route.query.t)
    const versionTag = Number.isFinite(queryBust) && queryBust > 0 ? queryBust : (stamp ? new Date(stamp).getTime() || Date.now() : Date.now())
    const absUrl = picked ? `${normalizeFilePath(picked)}?v=${versionTag}` : ''
    image.value = {
      ...emptyImage,
      ...data,
      url: absUrl,
      exif: data.exif || {},
      relations: {
        parent: data.relations?.parent
          ? {
              ...data.relations.parent,
              thumb: data.relations.parent.thumb ? `${normalizeFilePath(data.relations.parent.thumb)}?v=${versionTag}` : '',
            }
          : null,
        children: (data.relations?.children || []).map((c) => ({
          ...c,
          thumb: c.thumb ? `${normalizeFilePath(c.thumb)}?v=${versionTag}` : '',
        })),
      },
      tags: data.tags || [],
    }
    suggestedTags.value = data.suggested_tags || data.suggestedTags || []
    previewSrc.value = absUrl
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '加载图片详情失败')
    loadError.value = err?.response?.data?.error || err?.message || '加载失败'
  }
  loading.value = false
}

const refreshDetail = () => {
  loadDetail()
}

watch(
  () => [route.params.id, route.query.t],
  () => {
    refreshDetail()
  },
  { immediate: true }
)

watch(
  () => stageRef.value,
  (el) => {
    if (!el) return
    stageObserver = stageObserver || new ResizeObserver(() => nextTick(updateStageSize))
    stageObserver.observe(el)
    nextTick(updateStageSize)
  }
)

onMounted(() => {
  nextTick(updateStageSize)
})

onUnmounted(() => {
  if (stageObserver) {
    stageObserver.disconnect()
    stageObserver = null
  }
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
})

const goEdit = () => {
  router.push({ name: 'imageEdit', params: { id: route.params.id } })
}
</script>

<template>
  <div class="detail-page">
    <header class="detail-top">
      <div class="top-left">
        <el-button text class="back-btn" @click="onBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>返回</span>
        </el-button>
        <span class="divider">|</span>
        <span class="title">{{ image.title }}</span>
      </div>
      <div class="top-actions">
        <el-button text type="primary" :icon="MagicStick" @click="goEdit">图片编辑</el-button>
        <el-button text :icon="Download" @click="onDownload">下载</el-button>
        <el-button text type="danger" :icon="DeleteIcon" @click="onDelete">删除</el-button>
      </div>
    </header>

    <!-- 左侧预览区 + 右侧信息与标签 -->
    <section class="detail-layout">
      <div class="preview-column">
          <div class="panel preview-panel">
            <div class="panel-header">
              <span class="panel-title">预览</span>
              <div class="zoom-bar">
                <el-button text :icon="ZoomOut" @click="changeZoom(-10)" />
                <span class="zoom-text">{{ zoom }}%</span>
                <el-button text :icon="ZoomIn" @click="changeZoom(10)" />
                <el-button text :icon="FullScreen" @click="fitScreen">{{ fitLabel }}</el-button>
              </div>
            </div>
            <div class="preview-body" :class="fitMode === 'contain' ? 'contain-mode' : 'width-mode'">
              <el-skeleton v-if="loading" :rows="6" animated style="width:100%;height:360px;" />
              <div v-else ref="stageRef" class="img-stage" :class="fitMode === 'contain' ? 'contain-mode' : 'width-mode'">
                <div v-if="previewSrc && !loadError" class="img-holder" :style="previewHolderStyle">
                  <img
                    :key="previewKey"
                    :src="previewSrc"
                    :alt="image.title"
                    :style="previewImgStyle"
                    @load="onPreviewLoad"
                    @error="onImgError"
                  />
                </div>
                <div v-else class="empty-preview">
                  <p>{{ loadError || '暂无图片' }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

      <div class="side-column">
        <el-tabs v-model="activeTab" class="side-tabs">
          <el-tab-pane label="基本信息" name="basic">
            <div class="block">
              <el-form label-width="68px" size="default" @change="onFieldChange">
                <el-form-item label="标题">
                  <el-input v-model="image.title" placeholder="输入标题" />
                </el-form-item>
                <el-form-item label="描述">
                  <el-input v-model="image.description" type="textarea" :rows="3" placeholder="输入描述" />
                </el-form-item>
                <el-form-item label="可见性">
                  <el-select v-model="image.visibility" placeholder="选择可见性" @change="onFieldChange">
                    <el-option v-for="opt in visibilityOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </el-form-item>
              </el-form>
            </div>

            <div class="block">
              <div class="block-title">文件信息</div>
              <el-descriptions :column="1" border>
                <el-descriptions-item label="尺寸">{{ fileInfo.dimension }}</el-descriptions-item>
                <el-descriptions-item label="大小">{{ fileInfo.sizeText }}</el-descriptions-item>
                <el-descriptions-item label="格式">{{ image.format || '未知' }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ image.createdAt || '未知' }}</el-descriptions-item>
              </el-descriptions>
            </div>
          </el-tab-pane>

          <el-tab-pane label="标签" name="tags">
            <div class="block header-row">
              <div class="block-title">图片标签</div>
              <div class="tag-actions">
                <el-button text type="primary" :loading="aiTagLoading" @click="addAiTags">AI 添加</el-button>
                <el-button text type="primary" :loading="savingTag" @click="addTag">+ 添加标签</el-button>
              </div>
            </div>
            <div class="tag-list">
              <el-tag
                v-for="(tag, idx) in image.tags"
                :key="tag"
                closable
                class="tag-chip"
                :type="tagTypes[idx % tagTypes.length]"
                @close="removeTag(tag)"
              >
                {{ tag }}
              </el-tag>
              <div v-if="!image.tags.length" class="tag-empty">暂无标签，点击右上角添加</div>
            </div>
            <div v-if="suggestedTags.length" class="tag-suggest-row">
              <span class="suggest-title">AI 建议：</span>
              <div class="tag-suggest-list">
                <el-tag
                  v-for="tag in suggestedTags"
                  :key="tag"
                  type="warning"
                  class="tag-chip"
                  :disable-transitions="true"
                  :effect="image.tags.includes(tag) ? 'dark' : 'plain'"
                  :closable="false"
                  @click="image.tags.includes(tag) ? ElMessage.info('标签已存在') : addTag(tag)"
                >
                  {{ tag }}<span v-if="image.tags.includes(tag)"> · 已添加</span>
                </el-tag>
              </div>
            </div>
            <div class="add-tag-row">
              <el-input v-model="newTag" placeholder="输入新标签" @keyup.enter="addTag" />
              <el-button type="primary" :loading="savingTag" @click="addTag">添加</el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="EXIF" name="exif">
            <div class="block">
              <div class="block-title">拍摄信息</div>
              <div class="info-row"><span class="label">相机</span><span class="value">{{ image.exif?.camera || '未知' }}</span></div>
              <div class="info-row"><span class="label">镜头</span><span class="value">{{ image.exif?.lens || '未知' }}</span></div>
            </div>
            <div class="block">
              <div class="block-title">拍摄参数</div>
              <div class="info-column">
                <div class="info-row"><span class="label">焦距</span><span class="value">{{ image.exif?.focal || '未知' }}</span></div>
                <div class="info-row"><span class="label">光圈</span><span class="value">{{ image.exif?.aperture || '未知' }}</span></div>
                <div class="info-row"><span class="label">快门速度</span><span class="value">{{ image.exif?.shutter || '未知' }}</span></div>
                <div class="info-row"><span class="label">ISO</span><span class="value">{{ image.exif?.iso || '未知' }}</span></div>
              </div>
            </div>
            <div class="block">
              <div class="block-title">拍摄时间</div>
              <div class="info-row">
                <span class="label">时间</span>
                <span class="value">{{ image.exif?.takenAt || '未知' }}</span>
              </div>
            </div>
            <div class="block">
              <div class="block-title">GPS 位置信息</div>
              <div class="gps-note">为保护隐私，GPS 位置信息默认隐藏</div>
              <el-button type="warning" plain @click="toggleGps">{{ showGps ? '隐藏位置' : '显示位置' }}</el-button>
              <div v-if="showGps" class="gps-detail">
                <div class="info-row">
                  <span class="label">坐标</span>
                  <span class="value">{{ image.exif?.gps || '未提供' }}</span>
                </div>
                <div class="map-placeholder">TODO: 未来可以嵌入地图展示坐标</div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="派生关系" name="relations">
            <div class="relations">
              <div class="relation-block">
                <div class="block-title">父图</div>
                <div class="relation-card">
                  <img :src="image.relations?.parent?.thumb || image.url" alt="" />
                  <div>
                    <div class="relation-title">{{ image.relations?.parent?.title || '原始图片' }}</div>
                    <div class="relation-tag">原始图片</div>
                  </div>
                </div>
              </div>
              <div class="relation-block current">
                <div class="block-title">当前图片</div>
                <div class="relation-card current-card">
                  <div class="icon-box">🖼️</div>
                  <div>
                    <div class="relation-title">当前查看的图片</div>
                    <div class="relation-tag primary">当前节点</div>
                  </div>
                </div>
              </div>
              <div class="relation-block">
                <div class="block-title">子图 {{ image.relations?.children?.length ? `(${image.relations.children.length})` : '' }}</div>
                <div class="relation-card child-card" v-for="child in image.relations?.children || []" :key="child.title">
                  <img :src="child.thumb" alt="" />
                  <div>
                    <div class="relation-title">{{ child.title }}</div>
                    <div class="relation-tag">{{ child.tag }}</div>
                  </div>
                </div>
              </div>
              <div class="relation-footnote">
                <ol>
                  <li>派生图片是通过编辑操作（裁剪、旋转、滤镜等）生成的新图片。</li>
                  <li>每个派生图片会保留与原图的关联关系。</li>
                  <li>点击派生图片可查看详情并继续编辑。</li>
                </ol>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </section>

  </div>
</template>

<style scoped>
.detail-page {
  --header-h: 72px;
  background: #f5f7fa;
  height: 100vh;
  overflow: hidden;
  padding-bottom: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.detail-top {
  position: sticky;
  top: 0;
  z-index: 9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  flex: 0 0 var(--header-h);
}
.top-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.back-btn {
  color: #2c3e50;
}
.divider {
  color: #9ca3af;
}
.title {
  font-weight: 600;
  color: #1f2937;
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.detail-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
}
.preview-column {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.side-column {
  flex: 0 0 380px;
  max-width: 420px;
  min-width: 340px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
}
.preview-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.panel-title {
  font-weight: 600;
  color: #1f6feb;
}
.zoom-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.zoom-text {
  width: 56px;
  text-align: center;
  color: #374151;
}
.preview-body {
  background: linear-gradient(135deg, #eef2f7, #e5e7eb);
  border-radius: 10px;
  padding: 16px;
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
}
.preview-body.width-mode {
  overflow: auto;
}
.preview-body.contain-mode {
  overflow: hidden;
}
.img-stage {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.img-stage.width-mode {
  align-items: flex-start;
}
.empty-preview {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #9ca3af;
  font-size: 14px;
}
.img-holder {
  position: relative;
  display: inline-block;
  flex-shrink: 0;
}
.img-holder img {
  position: absolute;
  left: 50%;
  top: 50%;
  display: block;
  max-width: none;
  max-height: none;
  border-radius: 8px;
}
.side-tabs {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 10px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
:deep(.side-tabs .el-tabs__content) {
  flex: 1;
  overflow: auto;
}
.block {
  margin-bottom: 16px;
}
.block-title {
  font-weight: 600;
  color: #1f6feb;
  margin-bottom: 8px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.tag-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tag-list {
  display: flex;
  gap: 8px;
  flex-direction: column;
  margin-bottom: 12px;
}
.tag-suggest-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.tag-suggest-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.suggest-title {
  color: #f59e0b;
  font-weight: 600;
}
.tag-chip {
  display: inline-flex;
  width: fit-content;
}
.tag-empty {
  color: #9ca3af;
  font-size: 14px;
}
.add-tag-row {
  display: flex;
  gap: 8px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  color: #4b5563;
}
.info-row .label {
  color: #6b7280;
}
.info-column {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gps-note {
  background: #eef2f7;
  color: #1f6feb;
  padding: 8px 12px;
  border: 1px solid #d7e3f4;
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}
.gps-detail {
  margin-top: 10px;
}
.map-placeholder {
  margin-top: 6px;
  padding: 12px;
  background: #f2f4f8;
  border-radius: 8px;
  color: #6b7280;
  border: 1px dashed #d1d5db;
}
.relations {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.relation-block {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px;
}
.relation-card {
  display: flex;
  gap: 10px;
  align-items: center;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px;
}
.relation-card img {
  width: 80px;
  height: 60px;
  object-fit: cover;
  border-radius: 6px;
}
.relation-title {
  font-weight: 600;
  color: #1f2937;
}
.relation-tag {
  font-size: 13px;
  color: #6b7280;
}
.relation-tag.primary {
  color: #1f6feb;
}
.current-card {
  border: 1px solid #c7ddff;
  background: #eef4ff;
}
.icon-box {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #e0ecff;
  font-size: 22px;
}
.child-card {
  margin-top: 8px;
}
.relation-footnote {
  color: #6b7280;
  font-size: 13px;
}
.relation-footnote li {
  margin-left: 16px;
  line-height: 1.6;
}

.editor-dialog :deep(.el-dialog__body) {
  padding: 0;
}
.editor-dialog {
  --neutral-bg: #f5f7fa;
}
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 18px;
  background: var(--neutral-bg);
  border-bottom: 1px solid #e5e7eb;
}
.editor-title {
  font-weight: 700;
  color: #1f6feb;
}
.editor-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 16px;
  padding: 16px;
  background: var(--neutral-bg);
  height: calc(100vh - 96px);
  overflow: hidden;
}
.editor-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-width: 0;
}
.editor-right {
  min-width: 0;
  height: 100%;
}
.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
}
.crop-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.editor-stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: auto; /* 放大时可滚动查看 */
  min-height: 0;
}
.single-card {
  padding: 10px;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.editor-stage > .single-card,
.editor-stage > .compare-grid {
  width: 100%;
  height: 100%;
}
.neutral {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}
.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  width: 100%;
  height: 100%;
  align-items: center;
}
.single-card {
  padding: 10px;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.card {
  padding: 10px;
}
.card-title {
  font-weight: 600;
  color: #1f6feb;
  margin-bottom: 8px;
}
.card-img {
  position: relative;
  background: linear-gradient(135deg, #f4f6fb, #edf2ff);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 260px;
  width: 100%;
  height: 100%;
  overflow: auto; /* 放大时允许滚动 */
}
.card-img img {
  max-width: 100%;
  max-height: 100%;
  border-radius: 12px;
  object-fit: contain;
}
.crop-overlay {
  position: absolute;
  inset: 16px;
  pointer-events: none;
}
.crop-rect {
  position: absolute;
  border: 2px solid #1f6feb;
  border-radius: 4px;
  box-sizing: border-box;
  pointer-events: auto;
}
.crop-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  pointer-events: none;
}
.crop-rect .handle {
  position: absolute;
  width: 12px;
  height: 12px;
  background: #1f6feb;
  border: 2px solid #fff;
  border-radius: 50%;
  pointer-events: auto;
}
.handle-nw { top: -6px; left: -6px; cursor: nwse-resize; }
.handle-ne { top: -6px; right: -6px; cursor: nesw-resize; }
.handle-sw { bottom: -6px; left: -6px; cursor: nesw-resize; }
.handle-se { bottom: -6px; right: -6px; cursor: nwse-resize; }
.ratio-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.custom-ratio {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
}
.custom-label {
  color: #4b5563;
  font-size: 13px;
}
.colon {
  color: #6b7280;
}
.rotate-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.rotate-text {
  color: #1f6feb;
}
.rotate-slider {
  margin-top: 8px;
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0;
}
.slider-row span {
  width: 60px;
  color: #1f6feb;
}
.reset-row {
  justify-content: flex-end;
}
.export-row {
  margin-bottom: 10px;
}
.export-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}
.export-label {
  color: #4b5563;
  font-size: 13px;
}
.export-tip {
  font-size: 12px;
  color: #6b7280;
}
.export-actions {
  display: flex;
  gap: 10px;
}
.export-note {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
}
.right-scroll {
  height: 100%;
  padding-right: 8px;
}
.editor-right :deep(.el-scrollbar__wrap) {
  padding-right: 4px;
}
.editor-right :deep(.el-scrollbar__view) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 768px) {
  .detail-layout {
    flex-direction: column;
    padding: 12px 10px;
    gap: 12px;
  }

  .side-column {
    max-width: none;
    min-width: 0;
  }

  .panel {
    padding: 10px;
  }

  .panel-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .zoom-bar {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }

  .preview-body {
    min-height: 280px;
    padding: 12px;
  }

  .img-holder,
  .img-holder img {
    max-height: 60vh;
  }

  .editor-toolbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .editor-stage {
    padding: 16px;
  }

  .compare-grid {
    grid-template-columns: 1fr;
  }

  .export-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .export-actions {
    flex-wrap: wrap;
  }
}

@media (max-width: 1100px) {
  .detail-layout {
    flex-direction: column;
  }
  .preview-body {
    min-height: 320px;
  }
  .editor-body {
    grid-template-columns: 1fr;
    height: auto;
  }
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
