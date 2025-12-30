<script setup>
import { nextTick, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Plus, Loading } from '@element-plus/icons-vue'
import api from '../api/http'
import { AI_FILL_LABEL } from '../utils/useAiAnalyzer'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tagOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'uploaded'])

const visible = ref(false)
watch(
  () => props.modelValue,
  (v) => (visible.value = v),
  { immediate: true }
)
watch(visible, (v) => emit('update:modelValue', v))

const accept = '.jpg,.jpeg,.png,.gif,.webp'
const MAX_SIZE = 10 * 1024 * 1024
const defaultTags = ['风景', '人物', '美食', '建筑', '动物', '艺术', '科技', '运动', '旅行', '自然']
const allTags = computed(() => (props.tagOptions.length ? props.tagOptions : defaultTags))

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
const missingCount = computed(() => missingIndices.value.length)
const titlePlaceholder = computed(() => {
  const name = selectedItem.value?.file?.name
  return name ? `默认使用文件名：${name}` : '输入标题'
})

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

const formatExifDate = (value) => {
  if (!value) return ''
  if (value instanceof Date) return value.toLocaleString()
  const dt = new Date(value)
  if (!Number.isNaN(dt.getTime())) return dt.toLocaleString()
  return String(value)
}

let exifrModule = null
const loadExifr = async () => {
  if (exifrModule) return exifrModule
  try {
    const mod = await import(
      /* @vite-ignore */ 'https://cdn.jsdelivr.net/npm/exifr@7.1.3/dist/exifr.esm.js'
    )
    exifrModule = mod?.default || mod
  } catch (e) {
    exifrModule = null
  }
  return exifrModule
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
    item.meta.exif = {
      camera,
      lens,
      focalLength: data.FocalLength ? `${data.FocalLength}mm` : '',
      aperture: data.FNumber ? `f/${Number(data.FNumber).toFixed(1)}` : '',
      shutter: data.ExposureTime ? String(data.ExposureTime) : '',
      iso: data.ISO ? String(data.ISO) : '',
      datetime: formatExifDate(data.DateTimeOriginal || data.CreateDate || data.ModifyDate),
      gps,
    }
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

const clearSelection = () => {
  reset()
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
  if (!pendingFiles.value.length) return
  uploading.value = true
  let successCount = 0
  for (const item of pendingFiles.value) {
    item.status = 'uploading'
    try {
      const resp = await uploadOne(item)
      item.serverUrl = resp.thumb_url || resp.url || item.serverUrl || item.url
      item.imageId = resp.image_id || resp.id || item.imageId || null
      item.duplicated = !!resp.duplicated
      item.status = 'done'
      successCount += 1
    } catch (e) {
      item.status = 'error'
      ElMessage.error(e?.response?.data?.error || `上传失败：${item.file?.name || ''}`)
    }
  }
  uploading.value = false
  if (successCount) {
    ElMessage.success('上传成功')
    emit('uploaded', { count: successCount })
    visible.value = false
    reset()
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

const onCancel = () => {
  visible.value = false
  reset()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="上传图片"
    width="860px"
    :close-on-click-modal="false"
    @close="onCancel"
    destroy-on-close
  >
    <div class="dialog-grid">
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
                <div class="msg">拖拽图片到此处，或 <span class="link">点击上传</span></div>
                <div class="tips">支持 JPG、PNG、GIF、WEBP 格式，单个文件不超过 10MB</div>
              </div>
            </el-upload>
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
        </div>

        <div v-if="pendingFiles.length" class="thumb-strip">
          <div
            v-for="(item, idx) in pendingFiles"
            :key="item.id"
            class="thumb-card"
            :class="{ active: idx === selectedIndex }"
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
                  placeholder="添加描述信息..."
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
                  placeholder="选择或输入标签"
                  @change="clearFieldError('tags')"
                  style="width: 100%;"
                >
                  <el-option v-for="t in allTags" :key="t" :label="t" :value="t" />
                </el-select>
                <div v-if="selectedItem.errors?.tags" class="field-error">请至少添加一个标签</div>
              </el-form-item>
            </div>
            <el-form-item label="可见性">
              <el-select v-model="selectedItem.form.visibility" placeholder="选择可见性" style="width: 100%;">
                <el-option label="仅自己可见" value="private" />
                <el-option label="公开" value="public" />
              </el-select>
            </el-form-item>
          </template>
          <div v-else class="empty-form">先选择图片，再完善元信息</div>
        </el-form>
      </div>
    </div>

    <template #footer>
      <div class="footer">
        <el-button @click="onCancel">取消</el-button>
        <el-button :disabled="!pendingFiles.length || uploading || analyzingActive" @click="clearSelection">清空选择</el-button>
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
          :disabled="!pendingFiles.length || analyzingActive || aiProcessing"
          :loading="uploading"
          @click="handleStartUpload"
        >
          开始上传
        </el-button>
      </div>
    </template>

    <el-dialog
      v-model="incompleteDialogVisible"
      title="信息尚未完善"
      width="420px"
      append-to-body
    >
      <div class="dialog-body">还有 {{ missingCount }} 张图片未完善信息，可继续设置或使用 AI 智能分析补全。</div>
      <template #footer>
        <el-button @click="goToFirstIncomplete">继续设置</el-button>
        <el-button type="primary" :loading="aiProcessing" @click="autoFillIncomplete">{{ AI_FILL_LABEL }}</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.upload-box :deep(.el-upload) {
  width: 100%;
}

.dialog-grid {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 16px;
}

.preview-column,
.form-column {
  min-width: 0;
}

.preview-panel {
  position: relative;
  background: #fff;
  border: 1px dashed #d1d5db;
  border-radius: 12px;
  padding: 12px;
  min-height: 240px;
}

.preview-panel.dragging {
  border-color: #7fa8ff;
  box-shadow: 0 0 0 2px rgba(127, 168, 255, 0.2);
}

.preview-stage {
  height: 260px;
  border-radius: 10px;
  background: #f8fbff;
  border: 1px solid #e5e7eb;
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
  color: #9aa0a6;
}

.preview-status {
  position: absolute;
  right: 12px;
  top: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  color: #3b82f6;
}

.preview-status .spin {
  animation: spin 1s linear infinite;
}

.drop-mask {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.08);
  display: grid;
  place-items: center;
  font-weight: 600;
  color: #3b82f6;
}

.drag-area {
  border: 2px dashed #d1d5db;
  border-radius: 12px;
  background: #fafbff;
  text-align: center;
  padding: 20px 10px;
}

.icon {
  font-size: 38px;
  color: #90a4f6;
  margin-bottom: 6px;
}

.msg {
  color: #374151;
}

.msg .link {
  color: #2563eb;
  cursor: pointer;
}

.tips {
  color: #9aa0a6;
  font-size: 12px;
  margin-top: 6px;
}

.add-more {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.add-btn {
  border-radius: 999px;
  height: 30px;
  padding: 0 12px;
}

.hidden-input {
  display: none;
}

.thumb-strip {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 8px 0 4px;
  max-width: 100%;
}

.thumb-card {
  position: relative;
  min-width: 150px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex: 0 0 auto;
}

.thumb-card.active {
  border-color: #7fa8ff;
  box-shadow: 0 8px 16px rgba(75, 140, 255, 0.16);
}

.thumb-image {
  width: 44px;
  height: 44px;
  border-radius: 8px;
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
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}

.thumb-meta {
  color: #6b7280;
  font-size: 12px;
  margin-top: 2px;
}

.thumb-remove {
  position: absolute;
  right: 6px;
  top: 6px;
  border: none;
  background: rgba(0, 0, 0, 0.05);
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  color: #6b7280;
}

.form-column {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
}

.form-title {
  font-weight: 700;
  color: #3b82f6;
  margin-bottom: 6px;
}

.form-body :deep(.el-input__wrapper),
.form-body :deep(.el-textarea__inner),
.form-body :deep(.el-select .el-input__wrapper) {
  border-color: #e5e7eb;
  background: #fff;
}

.field-error {
  margin-top: 6px;
  font-size: 12px;
  color: #ef4444;
}

.empty-form {
  padding: 10px;
  color: #6b7280;
  background: #f8fafc;
  border-radius: 10px;
}

.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.glossy-btn {
  background: linear-gradient(135deg, #60a5fa, #2563eb) !important;
  border: none !important;
  color: #fff !important;
  box-shadow: 0 8px 16px rgba(59, 130, 246, 0.26);
}

.glossy-btn:hover {
  box-shadow: 0 10px 18px rgba(59, 130, 246, 0.3);
}

.dialog-body {
  color: #111827;
  line-height: 1.6;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .dialog-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .preview-stage {
    height: 200px;
  }

  .thumb-card {
    min-width: 130px;
  }
}
</style>
