<script setup>
import { nextTick, ref, computed } from 'vue'
import { useRouter, isNavigationFailure, NavigationFailureType } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, Plus, Loading } from '@element-plus/icons-vue'
import * as exifr from 'exifr'
import api from '../api/http'

const router = useRouter()

const accept = '.jpg,.jpeg,.png,.gif,.webp'
const MAX_SIZE = 10 * 1024 * 1024
const defaultTags = ['风景', '人物', '美食', '建筑', '动物', '艺术', '科技', '旅行', '自然']
const tagOptions = computed(() => defaultTags)

const uploadRef = ref(null)
const fileInputRef = ref(null)
const folderInputRef = ref(null)
const descRef = ref(null)
const tagsRef = ref(null)

const pendingFiles = ref([])
const selectedIndex = ref(0)
const dragging = ref(false)
const uploading = ref(false)
const analyzingActive = ref(false)
const aiProcessing = ref(false)
const incompleteDialogVisible = ref(false)
const missingIndices = ref([])

const selectedItem = computed(() => pendingFiles.value[selectedIndex.value] || null)
const selectedMeta = computed(() => selectedItem.value?.meta || {})
const selectedExif = computed(() => selectedMeta.value?.exif || {})
const missingCount = computed(() => missingIndices.value.length)
const titlePlaceholder = computed(() => {
  const name = selectedItem.value?.file?.name
  return name ? `默认使用文件名：${name}` : '输入标题'
})

const gpsAvailable = computed(() => !!selectedExif.value?.gps)
const gpsVisible = computed(() => !!selectedMeta.value?.gpsVisible)
const gpsButtonText = computed(() => (gpsVisible.value ? '隐藏位置' : '显示位置'))
const gpsText = computed(() => {
  if (!gpsAvailable.value) return '无 GPS 信息'
  if (!gpsVisible.value) return '为保护隐私，GPS 位置信息默认隐藏'
  const gps = selectedExif.value.gps
  if (!gps) return '无 GPS 信息'
  const lat = typeof gps.lat === 'number' ? gps.lat.toFixed(5) : gps.lat
  const lng = typeof gps.lng === 'number' ? gps.lng.toFixed(5) : gps.lng
  return `${lat}, ${lng}`
})

const displayResolution = computed(() => {
  const width = selectedMeta.value?.width
  const height = selectedMeta.value?.height
  return width && height ? `${width} x ${height}` : '--'
})
const displaySize = computed(() => {
  const sizeMB = selectedMeta.value?.sizeMB
  return typeof sizeMB === 'number' ? `${sizeMB.toFixed(2)} MB` : '--'
})
const displayFormat = computed(() => selectedMeta.value?.format || '--')
const displayCreatedAt = computed(() => selectedMeta.value?.createdAt || '--')
const displayCamera = computed(() => selectedExif.value?.camera || '--')
const displayLens = computed(() => selectedExif.value?.lens || '--')
const displayFocal = computed(() => selectedExif.value?.focalLength || '--')
const displayAperture = computed(() => selectedExif.value?.aperture || '--')
const displayShutter = computed(() => selectedExif.value?.shutter || '--')
const displayIso = computed(() => selectedExif.value?.iso || '--')
const displayExifTime = computed(() => selectedExif.value?.datetime || '--')

const genId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `u_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

const revokeUrl = (url) => {
  try {
    url && URL.revokeObjectURL(url)
  } catch (e) {}
}

const validateFile = (file, silent = false) => {
  const okType = /image\/(jpeg|png|gif|webp)/i.test(file.type) || /\.(jpe?g|png|gif|webp)$/i.test(file.name)
  if (!okType) {
    if (!silent) ElMessage.error('仅支持 JPG/PNG/GIF/WEBP 格式')
    return false
  }
  if (file.size > MAX_SIZE) {
    if (!silent) ElMessage.error('单个文件不能超过 10MB')
    return false
  }
  return true
}

const formatSizeMB = (size) => Number((size / 1024 / 1024).toFixed(2))

const formatFormat = (file) => {
  const type = file.type?.split('/')?.[1]
  if (type) return type.toUpperCase()
  const ext = file.name?.split('.')?.pop()
  return ext ? ext.toUpperCase() : '--'
}

const formatDate = (value) => {
  if (!value) return '--'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '--'
  return dt.toLocaleString()
}

const formatAperture = (value) => {
  if (value === undefined || value === null || value === '') return ''
  const num = Number(value)
  if (!Number.isNaN(num)) return `f/${num.toFixed(1)}`
  return `f/${value}`
}

const formatShutter = (value) => {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'number') {
    if (value >= 1) return `${value.toFixed(1)}s`
    const denom = Math.round(1 / value)
    return `1/${denom}s`
  }
  if (typeof value === 'string') return value
  if (value?.numerator && value?.denominator) return `${value.numerator}/${value.denominator}s`
  return String(value)
}

const formatFocal = (value) => {
  if (value === undefined || value === null || value === '') return ''
  const num = Number(value)
  if (!Number.isNaN(num)) return `${num.toFixed(0)}mm`
  return String(value)
}

const formatExifDate = (value) => {
  if (!value) return ''
  if (value instanceof Date) return value.toLocaleString()
  const dt = new Date(value)
  if (!Number.isNaN(dt.getTime())) return dt.toLocaleString()
  return String(value)
}

const hasExifValue = (exif = {}) =>
  !!(
    exif.camera ||
    exif.lens ||
    exif.focalLength ||
    exif.aperture ||
    exif.shutter ||
    exif.iso ||
    exif.datetime ||
    exif.gps
  )

const normalizeServerExif = (exif = {}) => ({
  camera: exif.camera || '',
  lens: exif.lens || '',
  focalLength: exif.focalLength || (exif.focal ? formatFocal(exif.focal) : ''),
  aperture: exif.aperture || (exif.fNumber ? formatAperture(exif.fNumber) : ''),
  shutter: exif.shutter || (exif.exposureTime ? formatShutter(exif.exposureTime) : ''),
  iso: exif.iso ? String(exif.iso) : '',
  datetime: exif.datetime || '',
  gps: exif.gps || null,
})

const applyExif = (item, exif = {}) => {
  if (!item?.meta?.exif) return
  const next = normalizeServerExif(exif)
  item.meta.exif = {
    ...item.meta.exif,
    camera: next.camera || item.meta.exif.camera,
    lens: next.lens || item.meta.exif.lens,
    focalLength: next.focalLength || item.meta.exif.focalLength,
    aperture: next.aperture || item.meta.exif.aperture,
    shutter: next.shutter || item.meta.exif.shutter,
    iso: next.iso || item.meta.exif.iso,
    datetime: next.datetime || item.meta.exif.datetime,
    gps: next.gps ?? item.meta.exif.gps ?? null,
  }
}

const fetchExifFromServer = async (item) => {
  if (!item?.file) return false
  try {
    const fd = new FormData()
    fd.append('file', item.file)
    const { data } = await api.post('/api/images/exif/preview', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 20000,
    })
    if (data?.ok === false) return false
    applyExif(item, data?.exif || {})
    return hasExifValue(item.meta.exif)
  } catch (e) {
    return false
  }
}

const loadExifr = async () => {
  const mod = exifr?.default || exifr
  if (!mod) return null
  if (typeof mod.parse === 'function') return mod
  if (typeof mod === 'function') return { parse: mod }
  return null
}

const buildItem = (file) => ({
  id: genId(),
  file,
  url: URL.createObjectURL(file),
  form: {
    title: '',
    description: '',
    tags: [],
    visibility: 'private',
  },
  meta: {
    width: null,
    height: null,
    sizeMB: formatSizeMB(file.size),
    format: formatFormat(file),
    createdAt: formatDate(file.lastModified),
    gpsVisible: false,
    exif: {
      camera: '',
      lens: '',
      focalLength: '',
      aperture: '',
      shutter: '',
      iso: '',
      datetime: '',
      gps: null,
    },
  },
  errors: {},
  status: 'pending',
  serverUrl: '',
  imageId: null,
  duplicated: false,
})

const loadImageSize = (item) =>
  new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      item.meta.width = img.width
      item.meta.height = img.height
      resolve()
    }
    img.onerror = () => resolve()
    img.src = item.url
  })

const hydrateMeta = async (item) => {
  await loadImageSize(item)
  const serverOk = await fetchExifFromServer(item)
  if (serverOk) return
  try {
    const exifr = await loadExifr()
    if (!exifr?.parse) return
    const data = await exifr.parse(item.file, {
      pick: [
        'Make',
        'Model',
        'LensMake',
        'LensModel',
        'FocalLength',
        'FNumber',
        'ExposureTime',
        'ISO',
        'DateTimeOriginal',
        'CreateDate',
        'ModifyDate',
        'GPSLatitude',
        'GPSLongitude',
      ],
    })
    if (!data) return
    const camera = [data.Make, data.Model].filter(Boolean).join(' ')
    const lens = [data.LensMake, data.LensModel].filter(Boolean).join(' ')
    const gps =
      typeof data.GPSLatitude === 'number' && typeof data.GPSLongitude === 'number'
        ? { lat: data.GPSLatitude, lng: data.GPSLongitude }
        : null
    applyExif(item, {
      camera,
      lens,
      focalLength: formatFocal(data.FocalLength),
      aperture: formatAperture(data.FNumber),
      shutter: formatShutter(data.ExposureTime),
      iso: data.ISO ? String(data.ISO) : '',
      datetime: formatExifDate(data.DateTimeOriginal || data.CreateDate || data.ModifyDate),
      gps,
    })
  } catch (e) {
    // 解析失败保持默认值
  }
}

const addFiles = (files) => {
  const list = Array.from(files || []).filter(Boolean)
  if (!list.length) return
  let added = 0
  list.forEach((file) => {
    if (!validateFile(file)) return
    const item = buildItem(file)
    pendingFiles.value.push(item)
    added += 1
    void hydrateMeta(item)
  })
  if (added) {
    if (selectedIndex.value < 0 || selectedIndex.value >= pendingFiles.value.length) {
      selectedIndex.value = 0
    }
    nextTick(() => uploadRef.value?.clearFiles())
  }
}

const beforeUpload = (file) => validateFile(file, true)

const handleUploadChange = (file) => {
  if (file?.raw) addFiles([file.raw])
}

const onFilesPicked = (event) => {
  addFiles(event.target.files)
  event.target.value = ''
}

const onFolderPicked = (event) => {
  addFiles(event.target.files)
  event.target.value = ''
}

const onDrop = (event) => {
  dragging.value = false
  addFiles(event.dataTransfer?.files)
}

const onDragEnter = () => {
  dragging.value = true
}

const onDragLeave = () => {
  dragging.value = false
}

const setActive = (idx) => {
  selectedIndex.value = idx
}

const removeItem = (idx) => {
  const item = pendingFiles.value[idx]
  if (!item) return
  revokeUrl(item.url)
  pendingFiles.value.splice(idx, 1)
  if (!pendingFiles.value.length) {
    selectedIndex.value = 0
    return
  }
  if (selectedIndex.value >= pendingFiles.value.length) {
    selectedIndex.value = pendingFiles.value.length - 1
  }
}

const reset = () => {
  pendingFiles.value.forEach((item) => revokeUrl(item.url))
  pendingFiles.value = []
  selectedIndex.value = 0
  uploadRef.value?.clearFiles()
}

const clearFieldError = (field) => {
  if (!selectedItem.value?.errors) return
  if (field === 'description' && selectedItem.value.form.description.trim()) {
    selectedItem.value.errors.description = false
  }
  if (field === 'tags' && selectedItem.value.form.tags.length) {
    selectedItem.value.errors.tags = false
  }
}

const validateItem = (item) => {
  const errors = {}
  if (!item.form.description.trim()) errors.description = true
  if (!item.form.tags.length) errors.tags = true
  item.errors = errors
  return Object.keys(errors).length === 0
}

const validateQueue = () => {
  const missing = []
  pendingFiles.value.forEach((item, idx) => {
    if (!validateItem(item)) missing.push(idx)
  })
  missingIndices.value = missing
  return missing
}

const scrollToError = (item) => {
  nextTick(() => {
    if (item.errors?.description && descRef.value) {
      descRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    if (item.errors?.tags && tagsRef.value) {
      tagsRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

const goToFirstIncomplete = () => {
  if (!missingIndices.value.length) {
    incompleteDialogVisible.value = false
    return
  }
  const idx = missingIndices.value[0]
  selectedIndex.value = idx
  const item = pendingFiles.value[idx]
  incompleteDialogVisible.value = false
  if (item) scrollToError(item)
}

const toggleGps = () => {
  if (!selectedItem.value) return
  selectedItem.value.meta.gpsVisible = !selectedItem.value.meta.gpsVisible
}

const normalizeTags = (raw) => {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw.map((t) => String(t).trim()).filter(Boolean)
  }
  if (typeof raw === 'string') {
    return raw
      .split(/[，,、\s]+/)
      .map((t) => t.trim())
      .filter(Boolean)
  }
  return []
}

const analyzeItem = async (item) => {
  item.status = 'analyzing'
  try {
    const fd = new FormData()
    fd.append('file', item.file)
    const { data } = await api.post('/api/v1/images/ai-analyze', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 20000,
    })
    if (data?.ok === false) {
      throw new Error(data?.error || 'AI 分析失败')
    }
    const aiTitle = String(data?.title || '').trim()
    const aiDesc = String(data?.description || '').trim()
    const aiTags = normalizeTags(data?.tags || [])
    if (!item.form.title && aiTitle) item.form.title = aiTitle
    if (!item.form.description && aiDesc) item.form.description = aiDesc
    if (!item.form.tags.length && aiTags.length) item.form.tags = aiTags
    return true
  } catch (e) {
    ElMessage.error(e?.message || 'AI 分析失败')
    return false
  } finally {
    item.status = 'pending'
  }
}

const analyzeActive = async () => {
  const item = selectedItem.value
  if (!item) {
    ElMessage.warning('请先选择图片')
    return
  }
  if (!item.file) {
    ElMessage.error('未找到图片源文件')
    return
  }
  analyzingActive.value = true
  const ok = await analyzeItem(item)
  analyzingActive.value = false
  if (ok) {
    ElMessage.success('AI 已分析完成')
  }
}

const autoFillIncomplete = async () => {
  const missing = validateQueue()
  if (!missing.length) {
    incompleteDialogVisible.value = false
    return
  }
  aiProcessing.value = true
  for (const idx of missing) {
    const item = pendingFiles.value[idx]
    if (!item) continue
    await analyzeItem(item)
  }
  aiProcessing.value = false
  const left = validateQueue()
  if (!left.length) {
    incompleteDialogVisible.value = false
    await performUpload()
  } else {
    ElMessage.warning(`还有 ${left.length} 张图片未完善，请继续设置`)
    goToFirstIncomplete()
  }
}

const safeNavigate = async (target) => {
  try {
    await router.push(target)
  } catch (err) {
    if (!isNavigationFailure(err, NavigationFailureType.duplicated)) {
      console.error('[upload] navigation failed', err)
    }
  }
}

const applyUploadResult = (item, resp = {}) => {
  const serverUrl = resp.thumb_url || resp.url || item.serverUrl || item.url
  item.serverUrl = serverUrl
  item.imageId = resp.image_id || resp.id || item.imageId || null
  item.duplicated = !!resp.duplicated
  item.status = 'done'
}

const uploadOne = async (item) => {
  const fd = new FormData()
  fd.append('files', item.file)
  fd.append('title', item.form.title || '')
  fd.append('description', item.form.description || '')
  fd.append('tags', JSON.stringify(item.form.tags || []))
  fd.append('visibility', item.form.visibility || 'private')
  const { data } = await api.post('/api/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  const saved = data?.saved || data?.files || []
  return saved[0] || {}
}

const performUpload = async () => {
  if (!pendingFiles.value.length) {
    ElMessage.warning('请选择要上传的图片')
    return
  }
  uploading.value = true
  let successCount = 0
  for (const item of pendingFiles.value) {
    item.status = 'uploading'
    try {
      const resp = await uploadOne(item)
      applyUploadResult(item, resp)
      successCount += 1
    } catch (e) {
      item.status = 'error'
      ElMessage.error(e?.response?.data?.error || `上传失败：${item.file?.name || ''}`)
    }
  }
  uploading.value = false
  if (successCount) {
    ElMessage.success(`成功上传 ${successCount} 张图片`)
    const ids = pendingFiles.value.map((q) => q.imageId).filter(Boolean)
    await nextTick()
    if (successCount === 1 && pendingFiles.value.length === 1 && ids[0]) {
      await safeNavigate({ name: 'ImageDetail', params: { id: ids[0] } })
    } else {
      await safeNavigate({ name: 'gallery', query: { from: 'upload', t: Date.now() } })
    }
  }
}

const handleStartUpload = async () => {
  if (uploading.value || analyzingActive.value || aiProcessing.value) return
  if (!pendingFiles.value.length) {
    ElMessage.warning('请选择要上传的图片')
    return
  }
  const missing = validateQueue()
  if (missing.length) {
    incompleteDialogVisible.value = true
    return
  }
  await performUpload()
}
</script>

<template>
  <div class="upload-page">
    <div class="header">
      <div>
        <h2>上传中心 · 快来丰富你的专属图库吧！</h2>
        <p class="sub">支持拖拽或点击选择，批量编辑每张图片的元信息</p>
      </div>
      <el-tag type="success" effect="plain">使用现有上传接口</el-tag>
    </div>

    <div class="workspace">
      <div class="preview-column">
        <div
          class="preview-panel"
          :class="{ dragging }"
          @dragenter.prevent="onDragEnter"
          @dragover.prevent
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
        >
          <div v-if="!pendingFiles.length" class="preview-empty">
            <el-upload
              ref="uploadRef"
              class="upload-box"
              drag
              multiple
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="beforeUpload"
              :on-change="handleUploadChange"
              :accept="accept"
            >
              <div class="drag-area">
                <el-icon class="icon"><UploadFilled /></el-icon>
                <div class="msg">拖拽或轻点选择</div>
                <div class="tips">支持 JPG / PNG / GIF / WEBP，单个文件不超过 10MB</div>
              </div>
            </el-upload>
            <div class="helper">手机可直接拍照或从相册选择，支持批量拖入</div>
          </div>
          <div v-else class="preview-stage">
            <img v-if="selectedItem?.url" class="preview-image" :src="selectedItem.url" alt="preview" />
            <div v-else class="preview-placeholder">暂无预览</div>
            <div v-if="selectedItem?.status === 'analyzing'" class="preview-status">
              <el-icon class="spin"><Loading /></el-icon>
              AI 分析中...
            </div>
          </div>
          <div v-if="dragging" class="drop-mask">释放鼠标以添加图片</div>
        </div>

        <div class="add-more">
          <el-dropdown trigger="click">
            <el-button class="add-btn" type="primary" plain>
              <el-icon><Plus /></el-icon>
              继续添加图片
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="fileInputRef?.click()">选择文件</el-dropdown-item>
                <el-dropdown-item @click="folderInputRef?.click()">选择文件夹</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input
            ref="fileInputRef"
            class="hidden-input"
            type="file"
            multiple
            :accept="accept"
            @change="onFilesPicked"
          />
          <input
            ref="folderInputRef"
            class="hidden-input"
            type="file"
            multiple
            webkitdirectory
            @change="onFolderPicked"
          />
          <span class="add-tip">支持拖拽追加与文件夹批量导入</span>
        </div>

        <div v-if="pendingFiles.length" class="thumb-strip">
          <div
            v-for="(item, idx) in pendingFiles"
            :key="item.id"
            class="thumb-card"
            :class="{ active: idx === selectedIndex, busy: item.status === 'analyzing' || item.status === 'uploading' }"
            @click="setActive(idx)"
          >
            <div
              class="thumb-image"
              :style="item.url || item.serverUrl ? { backgroundImage: `url(${item.serverUrl || item.url})` } : {}"
            ></div>
            <div class="thumb-info">
              <div class="thumb-name">{{ item.file?.name || '--' }}</div>
              <div class="thumb-meta">
                {{ item.meta?.sizeMB ? `${item.meta.sizeMB.toFixed(2)} MB` : '--' }}
              </div>
            </div>
            <div v-if="item.status === 'analyzing'" class="thumb-state">AI</div>
            <div v-else-if="item.status === 'uploading'" class="thumb-state">上传中</div>
            <div v-else-if="item.status === 'done'" class="thumb-state done">完成</div>
            <div v-else-if="item.status === 'error'" class="thumb-state error">失败</div>
            <button class="thumb-remove" type="button" @click.stop="removeItem(idx)">×</button>
          </div>
        </div>
      </div>

      <div class="form-column">
        <div class="form-title">上传设置</div>
        <el-form label-position="top" class="form-body">
          <template v-if="selectedItem">
            <el-form-item label="标题">
              <el-input v-model="selectedItem.form.title" :placeholder="titlePlaceholder" />
            </el-form-item>
            <div ref="descRef">
              <el-form-item label="描述">
                <el-input
                  v-model="selectedItem.form.description"
                  type="textarea"
                  :rows="3"
                  placeholder="可用于图片指引，支持多行"
                  @input="clearFieldError('description')"
                />
                <div v-if="selectedItem.errors?.description" class="field-error">请填写简介</div>
              </el-form-item>
            </div>
            <div ref="tagsRef">
              <el-form-item label="标签">
                <el-select
                  v-model="selectedItem.form.tags"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  :max-collapse-tags="4"
                  :reserve-keyword="false"
                  placeholder="输入或选择标签"
                  @change="clearFieldError('tags')"
                >
                  <el-option v-for="t in tagOptions" :key="t" :label="t" :value="t" />
                </el-select>
                <div v-if="selectedItem.errors?.tags" class="field-error">请至少添加一个标签</div>
              </el-form-item>
            </div>
            <el-form-item label="可见性">
              <el-select v-model="selectedItem.form.visibility" placeholder="选择可见性">
                <el-option label="仅自己可见" value="private" />
                <el-option label="公开" value="public" />
              </el-select>
            </el-form-item>
            <div class="meta-card">
              <div class="meta-title">预览信息（文件）</div>
              <div class="meta-grid">
                <div class="meta-item">
                  <span>尺寸(px)</span>
                  <strong>{{ displayResolution }}</strong>
                </div>
                <div class="meta-item">
                  <span>大小</span>
                  <strong>{{ displaySize }}</strong>
                </div>
                <div class="meta-item">
                  <span>格式</span>
                  <strong>{{ displayFormat }}</strong>
                </div>
                <div class="meta-item">
                  <span>创建时间</span>
                  <strong>{{ displayCreatedAt }}</strong>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="empty-form">先选择图片，再完善元信息</div>
        </el-form>
        <div class="actions">
          <el-button @click="reset" :disabled="uploading || aiProcessing">清空选择</el-button>
          <el-button
            class="glossy-btn"
            type="primary"
            plain
            :disabled="!selectedItem || uploading || aiProcessing || analyzingActive"
            :loading="analyzingActive"
            @click="analyzeActive"
          >
            AI 智能分析
          </el-button>
          <el-button
            class="glossy-btn"
            type="primary"
            :loading="uploading"
            :disabled="!pendingFiles.length || analyzingActive || aiProcessing"
            @click="handleStartUpload"
          >
            开始上传
          </el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="incompleteDialogVisible" title="信息尚未完善" width="420px">
      <div class="dialog-body">还有 {{ missingCount }} 张图片未完善信息，可继续设置或使用 AI 智能分析补全。</div>
      <template #footer>
        <el-button @click="goToFirstIncomplete">继续设置</el-button>
        <el-button type="primary" :loading="aiProcessing" @click="autoFillIncomplete">AI 一键补全</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.upload-page {
  --primary: var(--app-primary);
  --primary-strong: var(--app-primary-strong);
  --soft: var(--app-primary-soft);
  --border: var(--app-border);
  --text: var(--app-text);
  --muted: var(--app-muted);
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 18px 28px;
  width: 100%;
  box-sizing: border-box;
  overflow-x: hidden;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px;
}

.header h2 {
  margin: 0;
  color: var(--primary-strong);
}

.sub {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 14px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 16px;
}

.preview-column,
.form-column {
  min-width: 0;
}

.preview-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-panel {
  position: relative;
  background: #fff;
  border: 1px dashed var(--border);
  border-radius: 16px;
  padding: 14px;
  min-height: 360px;
  box-shadow: 0 12px 26px rgba(75, 140, 255, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.preview-panel.dragging {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(75, 140, 255, 0.18);
}

.preview-empty {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.preview-stage {
  height: 420px;
  border-radius: 12px;
  background: linear-gradient(180deg, #f8fbff, #edf3ff);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.preview-placeholder {
  color: var(--muted);
}

.preview-status {
  position: absolute;
  right: 18px;
  top: 18px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 13px;
  color: var(--primary-strong);
}

.preview-status .spin {
  animation: spin 1s linear infinite;
}

.drop-mask {
  position: absolute;
  inset: 0;
  border-radius: 16px;
  background: rgba(59, 130, 246, 0.08);
  display: grid;
  place-items: center;
  font-weight: 700;
  color: var(--primary-strong);
}

.drag-area {
  border: 2px dashed rgba(75, 140, 255, 0.55);
  border-radius: 12px;
  background: #fff;
  text-align: center;
  padding: 32px 12px;
  color: var(--primary-strong);
}

.icon {
  font-size: 48px;
  color: var(--primary);
  margin-bottom: 6px;
}

.msg {
  font-weight: 700;
  font-size: 18px;
}

.tips {
  margin-top: 6px;
  color: var(--muted);
  font-size: 13px;
}

.helper {
  margin-top: 12px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

.add-more {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.add-btn {
  border-radius: 999px;
  height: 32px;
  padding: 0 14px;
}

.add-tip {
  color: var(--muted);
  font-size: 13px;
}

.hidden-input {
  display: none;
}

.thumb-strip {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  max-width: 100%;
}

.thumb-card {
  position: relative;
  min-width: 160px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  flex: 0 0 auto;
}

.thumb-card.active {
  border-color: var(--primary);
  box-shadow: 0 10px 20px rgba(75, 140, 255, 0.2);
  transform: translateY(-1px);
}

.thumb-card.busy {
  opacity: 0.8;
}

.thumb-image {
  width: 52px;
  height: 52px;
  border-radius: 10px;
  background: #f2f4f8;
  background-size: cover;
  background-position: center;
  flex-shrink: 0;
}

.thumb-info {
  flex: 1;
  min-width: 0;
}

.thumb-name {
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thumb-meta {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}

.thumb-state {
  position: absolute;
  right: 10px;
  bottom: 8px;
  font-size: 12px;
  color: var(--primary-strong);
}

.thumb-state.done {
  color: #10b981;
}

.thumb-state.error {
  color: #ef4444;
}

.thumb-remove {
  position: absolute;
  right: 8px;
  top: 6px;
  border: none;
  background: rgba(0, 0, 0, 0.05);
  width: 20px;
  height: 20px;
  border-radius: 50%;
  cursor: pointer;
  color: #6b7280;
}

.form-column {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 12px 26px rgba(75, 140, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-title {
  font-weight: 700;
  color: var(--primary-strong);
}

.form-body :deep(.el-input__wrapper),
.form-body :deep(.el-textarea__inner),
.form-body :deep(.el-select .el-input__wrapper) {
  border-color: var(--border);
  background: #fff;
}

.field-error {
  margin-top: 6px;
  font-size: 12px;
  color: #ef4444;
}

.empty-form {
  padding: 12px;
  color: var(--muted);
  background: #f8fafc;
  border-radius: 12px;
}

.meta-card {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: linear-gradient(180deg, #f8fbff, #edf3ff);
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
  color: var(--text);
}

.meta-title {
  font-weight: 700;
  color: var(--primary-strong);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: var(--muted);
}

.meta-item strong {
  color: var(--text);
  font-weight: 600;
}

.meta-divider {
  height: 1px;
  background: rgba(148, 163, 184, 0.3);
}

.meta-gps {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
}

.meta-gps-text {
  flex: 1;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: auto;
  flex-wrap: wrap;
}

.glossy-btn {
  background: linear-gradient(135deg, #60a5fa, #2563eb) !important;
  border: none !important;
  color: #fff !important;
  box-shadow: 0 10px 18px rgba(59, 130, 246, 0.28);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.glossy-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 24px rgba(59, 130, 246, 0.32);
}

.glossy-btn:active {
  transform: translateY(1px);
  box-shadow: 0 8px 16px rgba(59, 130, 246, 0.2);
}

.dialog-body {
  color: var(--text);
  line-height: 1.6;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .actions {
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .upload-page {
    gap: 12px;
    padding: 0 14px 24px;
  }

  .header {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .preview-stage {
    height: 280px;
  }

  .thumb-card {
    min-width: 140px;
  }
}
</style>
