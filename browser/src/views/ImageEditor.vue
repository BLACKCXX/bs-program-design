<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ZoomOut, ZoomIn, FullScreen, RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import api from '../api/http'
import { toDisplayUrl } from '../utils/url'

const route = useRoute()
const router = useRouter()

const emptyImage = {
  id: null,
  title: '',
  description: '',
  url: '',
  width: null,
  height: null,
}

const image = ref({ ...emptyImage })
const previewUrl = ref('')
const previewKey = computed(() => `${previewUrl.value || 'empty'}`)
const loading = ref(false)
const loadError = ref('')
const blobUrl = ref('')
const previewLoading = ref(false)
const previewRequestSeq = ref(0)
const PREVIEW_TIMEOUT = 120000
const PREVIEW_DEBOUNCE = 180
let previewDebounceTimer = null
const isMobile = ref(false)
const updateIsMobile = () => {
  if (typeof window === 'undefined') return
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
}
let resizeHandler = null

const buildDefaultParams = () => ({
  deg: 0,
  crop_rect: null,
  target_width: null,
  target_height: null,
  keep_ratio: false,
  resize_mode: 'fit',
  brightness: 0,
  contrast: 0,
  saturation: 0,
  temperature: 0,
  sharpness: 0,
})
const editParams = ref(buildDefaultParams())
const previewAdjust = reactive({
  brightness: 0,
  contrast: 0,
  saturation: 0,
  temperature: 0,
  sharpness: 0,
})
const suppressPreviewAdjustWatch = ref(false)

const clampNumber = (val, min, max) => {
  const num = Number(val) || 0
  return Math.min(max, Math.max(min, num))
}

const buildAdjustValues = (source = {}) => ({
  brightness: Number(source.brightness) || 0,
  contrast: Number(source.contrast) || 0,
  saturation: Number(source.saturation) || 0,
  temperature: Number(source.temperature) || 0,
  sharpness: Number(source.sharpness) || 0,
})

const normalizeAdjustValues = (source = {}) => ({
  brightness: clampNumber(source.brightness, -100, 100),
  contrast: clampNumber(source.contrast, -100, 100),
  saturation: clampNumber(source.saturation, -100, 100),
  temperature: clampNumber(source.temperature, -100, 100),
  sharpness: clampNumber(source.sharpness, 0, 100),
})

const syncAdjustValues = (target, source = {}) => {
  const next = normalizeAdjustValues(source)
  target.brightness = next.brightness
  target.contrast = next.contrast
  target.saturation = next.saturation
  target.temperature = next.temperature
  target.sharpness = next.sharpness
}

const diffAdjustValues = (from, to) => {
  const base = buildAdjustValues(from)
  const next = buildAdjustValues(to)
  return {
    brightness: next.brightness - base.brightness,
    contrast: next.contrast - base.contrast,
    saturation: next.saturation - base.saturation,
    temperature: next.temperature - base.temperature,
    sharpness: next.sharpness - base.sharpness,
  }
}

const hasAdjustDelta = (delta) =>
  Boolean(
    Number(delta.brightness) ||
      Number(delta.contrast) ||
      Number(delta.saturation) ||
      Number(delta.temperature) ||
      Number(delta.sharpness)
  )

const resetPreviewAdjust = (source = editParams.value) => {
  suppressPreviewAdjustWatch.value = true
  syncAdjustValues(previewAdjust, source)
  nextTick(() => {
    suppressPreviewAdjustWatch.value = false
  })
}

const pendingAdjustDelta = computed(() => diffAdjustValues(editParams.value, previewAdjust))
const hasPreviewAdjust = computed(() => hasAdjustDelta(pendingAdjustDelta.value))
const historyStates = ref([JSON.parse(JSON.stringify(editParams.value))])
const historyIndex = ref(0)
const canUndo = computed(() => historyIndex.value > 0)
const canRedo = computed(() => historyIndex.value < historyStates.value.length - 1)

const zoom = ref(100)
const changeZoom = (delta) => {
  const next = Math.min(200, Math.max(33, zoom.value + delta))
  if (next === zoom.value) return
  zoom.value = next
}
const fitScreen = () => {
  if (zoom.value === 100) return
  zoom.value = 100
}

const normalizeFilePath = (p = '') => {
  if (!p) return ''
  const raw = String(p).trim()
  if (/^https?:\/\//i.test(raw) || raw.startsWith('blob:') || raw.startsWith('data:') || raw.startsWith('//')) {
    return raw
  }
  const normalized = toDisplayUrl(raw)
  let clean = normalized.replace(/\\/g, '/').replace(/^\/+/, '')
  clean = clean.replace(/^files\//, '')
  return toDisplayUrl(`/files/${encodeURI(clean)}`)
}

const pickUrl = (data = {}) =>
  data.absolute_url ||
  data.absoluteUrl ||
  data.url ||
  data.cover_url ||
  data.thumb_url ||
  data.stored_path ||
  data.path ||
  data.thumb ||
  ''

const resolveError = (err, fallback = '请求失败') =>
  err?.response?.data?.error || err?.response?.data?.detail || err?.message || fallback

const cloneParams = (params) => JSON.parse(JSON.stringify(params))

const isDefaultParams = (params) => {
  if (!params) return true
  const crop = params.crop_rect
  const cropW = crop ? Number(crop.w ?? crop.width) : 0
  const cropH = crop ? Number(crop.h ?? crop.height) : 0
  const resizeMode = (params.resize_mode || 'fit').toLowerCase()
  return (
    !Number(params.deg) &&
    !(cropW || cropH) &&
    !Number(params.target_width) &&
    !Number(params.target_height) &&
    !Boolean(params.keep_ratio) &&
    resizeMode === 'fit' &&
    !Number(params.brightness) &&
    !Number(params.contrast) &&
    !Number(params.saturation) &&
    !Number(params.temperature) &&
    !Number(params.sharpness)
  )
}

const buildPreviewPayload = (options = {}) => {
  const payload = cloneParams(editParams.value)
  const usePreviewAdjust = options.usePreviewAdjust !== false
  if (usePreviewAdjust) {
    const adjust = normalizeAdjustValues(previewAdjust)
    payload.brightness = adjust.brightness
    payload.contrast = adjust.contrast
    payload.saturation = adjust.saturation
    payload.temperature = adjust.temperature
    payload.sharpness = adjust.sharpness
  }
  return payload
}

const resetPreviewToBase = () => {
  previewRequestSeq.value += 1
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
  previewUrl.value = image.value.url || ''
  previewLoading.value = false
}

// Guard against stale preview responses when users click quickly.
const renderPreview = async (options = {}) => {
  if (!image.value.id) return
  const payload = buildPreviewPayload(options)
  if (isDefaultParams(payload)) {
    resetPreviewToBase()
    return
  }
  const seq = ++previewRequestSeq.value
  previewLoading.value = true
  try {
    const resp = await api.post(`/api/images/${image.value.id}/preview`, payload, {
      responseType: 'blob',
      timeout: PREVIEW_TIMEOUT,
    })
    if (seq !== previewRequestSeq.value) {
      if (resp?.data) {
        const tmpUrl = URL.createObjectURL(resp.data)
        URL.revokeObjectURL(tmpUrl)
      }
      return
    }
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = ''
    }
    blobUrl.value = URL.createObjectURL(resp.data)
    previewUrl.value = blobUrl.value
  } catch (err) {
    if (seq !== previewRequestSeq.value) return
    console.error('[editor] preview render failed', err)
    ElMessage.warning('预览生成失败，可继续编辑或重试')
    resetPreviewToBase()
  } finally {
    if (seq === previewRequestSeq.value) {
      previewLoading.value = false
    }
  }
}

const schedulePreview = (options = {}) => {
  if (previewDebounceTimer) {
    clearTimeout(previewDebounceTimer)
  }
  previewDebounceTimer = setTimeout(() => {
    previewDebounceTimer = null
    renderPreview(options)
  }, PREVIEW_DEBOUNCE)
}

const onImgError = () => {
  const fallbackUrl = image.value.url || ''
  if (fallbackUrl && previewUrl.value !== fallbackUrl) {
    resetPreviewToBase()
    return
  }
  loadError.value = loadError.value || '图片加载失败'
}

const getFromQuery = () => (typeof route.query.from === 'string' ? route.query.from : '')
const buildDetailQuery = (stamp = Date.now()) => {
  const query = { t: stamp }
  const from = getFromQuery()
  if (from) query.from = from
  return query
}

const pushHistory = () => {
  const snapshot = cloneParams(editParams.value)
  const current = historyStates.value[historyIndex.value]
  if (current && JSON.stringify(snapshot) === JSON.stringify(current)) return false
  if (historyIndex.value < historyStates.value.length - 1) {
    historyStates.value = historyStates.value.slice(0, historyIndex.value + 1)
  }
  historyStates.value.push(snapshot)
  historyIndex.value = historyStates.value.length - 1
  return true
}

const applyHistoryState = (state) => {
  editParams.value = cloneParams(state)
  resetPreviewAdjust()
}

const resetHistory = () => {
  historyStates.value = [cloneParams(editParams.value)]
  historyIndex.value = 0
}

const undo = async () => {
  if (!canUndo.value) return
  historyIndex.value -= 1
  applyHistoryState(historyStates.value[historyIndex.value])
  isCropping.value = false
  isScaling.value = false
  await renderPreview()
}

const redo = async () => {
  if (!canRedo.value) return
  historyIndex.value += 1
  applyHistoryState(historyStates.value[historyIndex.value])
  isCropping.value = false
  isScaling.value = false
  await renderPreview()
}

const loadDetail = async () => {
  loading.value = true
  loadError.value = ''
  previewUrl.value = ''
  endScaleDrag()
  previewLoading.value = false
  updateIsMobile()

  let data = null
  try {
    const resp = await api.get(`/api/images/${route.params.id}`)
    data = resp.data
  } catch (err) {
    const msg = resolveError(err, '加载图片详情失败')
    loadError.value = `[detail] ${msg}`
    ElMessage.error(msg)
    loading.value = false
    return
  }

  const picked = pickUrl(data)
  const stamp =
    data.updated_at ||
    data.updatedAt ||
    data.updated ||
    data.created_at ||
    data.createdAt
  const versionTag = stamp ? new Date(stamp).getTime() || Date.now() : Date.now()
  const absUrl = picked ? `${normalizeFilePath(picked)}?v=${versionTag}` : ''
  image.value = {
    ...emptyImage,
    ...data,
    url: absUrl,
  }
  resetPreviewToBase()
  editParams.value = buildDefaultParams()
  resetHistory()
  resetPreviewAdjust()
  imgNatural.value = { w: 0, h: 0 }
  cropRect.value = { x: 0, y: 0, width: 0, height: 0 }
  isCropping.value = false
  isScaling.value = false
  scaleRect.value = { width: 0, height: 0 }
  scaleBase.value = { w: 0, h: 0 }
  zoom.value = 100
  exportName.value = image.value.title || ''
  loading.value = false
}

// ---- 编辑状态 ----
const isCropping = ref(false)
const cropRect = ref({ x: 0, y: 0, width: 0, height: 0 })
const dragState = ref(null)

const MIN_SCALE_PX = 16
const MAX_SCALE_PX = 8192

const isScaling = ref(false)
const scaleRect = ref({ width: 0, height: 0 })
const scaleBase = ref({ w: 0, h: 0 })
const scaleDragState = ref(null)

const imgEl = ref(null)
const imgNatural = ref({ w: 0, h: 0 })
const imgBox = ref({ w: 0, h: 0 })
const stageRef = ref(null)
const stageSize = ref({ w: 0, h: 0 })
let stageObserver = null

const bboxSize = computed(() => {
  const w = imgNatural.value.w
  const h = imgNatural.value.h
  if (!w || !h) return { w: 0, h: 0 }
  return { w, h }
})
const fitScale = computed(() => {
  const w = stageSize.value.w
  const h = stageSize.value.h
  const bw = bboxSize.value.w
  const bh = bboxSize.value.h
  if (!w || !h || !bw || !bh) return 1
  const fitW = w / bw
  const fitH = h / bh
  return (isMobile.value ? fitW : Math.min(fitW, fitH)) * 0.98
})
const renderScale = computed(() => fitScale.value * (zoom.value / 100))
const scaleRatioX = computed(() => {
  if (!isScaling.value) return 1
  const baseW = scaleBase.value.w
  if (!baseW) return 1
  return scaleRect.value.width / baseW
})
const scaleRatioY = computed(() => {
  if (!isScaling.value) return 1
  const baseH = scaleBase.value.h
  if (!baseH) return 1
  return scaleRect.value.height / baseH
})
const displayScaleX = computed(() => renderScale.value * scaleRatioX.value)
const displayScaleY = computed(() => renderScale.value * scaleRatioY.value)
const holderStyle = computed(() => {
  if (!bboxSize.value.w || !bboxSize.value.h) return {}
  return {
    width: `${bboxSize.value.w * displayScaleX.value}px`,
    height: `${bboxSize.value.h * displayScaleY.value}px`,
  }
})
const imgStyle = computed(() => ({
  width: imgNatural.value.w ? `${imgNatural.value.w}px` : undefined,
  height: imgNatural.value.h ? `${imgNatural.value.h}px` : undefined,
  transform: `translate(-50%, -50%) scale(${displayScaleX.value}, ${displayScaleY.value})`,
  transformOrigin: 'center center',
}))

const syncImgBox = () => {
  const rect = imgEl.value?.getBoundingClientRect()
  if (!rect) return
  imgBox.value = { w: rect.width, h: rect.height }
}

const updateStageSize = () => {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) return
  stageSize.value = { w: rect.width, h: rect.height }
}

const getWorkingNatural = () => {
  if (imgNatural.value.w && imgNatural.value.h) return imgNatural.value
  return { w: image.value.width || 0, h: image.value.height || 0 }
}

const initCropRect = () => {
  const natural = getWorkingNatural()
  if (!natural.w || !natural.h) return
  const width = natural.w * 0.6
  const height = natural.h * 0.6
  const x = (natural.w - width) / 2
  const y = (natural.h - height) / 2
  cropRect.value = { x, y, width, height }
}

const onEditorImgLoad = async (e) => {
  const el = e.target
  imgNatural.value = { w: el.naturalWidth, h: el.naturalHeight }
  await nextTick()
  updateStageSize()
  syncImgBox()
}

watch(
  () => [
    previewAdjust.brightness,
    previewAdjust.contrast,
    previewAdjust.saturation,
    previewAdjust.temperature,
    previewAdjust.sharpness,
  ],
  () => {
    if (suppressPreviewAdjustWatch.value) return
    schedulePreview({ usePreviewAdjust: true })
  }
)

watch([zoom, isCropping, isScaling], async () => {
  await nextTick()
  syncImgBox()
})


watch(
  () => stageRef.value,
  (el) => {
    if (!el) return
    stageObserver = stageObserver || new ResizeObserver(() => {
      updateStageSize()
      nextTick(syncImgBox)
    })
    stageObserver.observe(el)
    updateStageSize()
    nextTick(syncImgBox)
  }
)

onMounted(() => {
  updateIsMobile()
  resizeHandler = () => updateIsMobile()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  endScaleDrag()
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
    resizeHandler = null
  }
  if (stageObserver) {
    stageObserver.disconnect()
    stageObserver = null
  }
  if (previewDebounceTimer) {
    clearTimeout(previewDebounceTimer)
    previewDebounceTimer = null
  }
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
})


watch(
  () => route.params.id,
  () => {
    loadDetail()
  },
  { immediate: true }
)

const toggleCropMode = () => {
  if (!isCropping.value) {
    isScaling.value = false
    isCropping.value = true
    cropRect.value = { x: 0, y: 0, width: 0, height: 0 }
    if (!cropRect.value?.width || !cropRect.value?.height) {
      initCropRect()
    }
    return
  }
  isCropping.value = false
}

const cancelCrop = () => {
  isCropping.value = false
  initCropRect()
}

const clampCropRect = (rect, natural) => {
  if (!rect) return rect
  let { x, y, width, height } = rect
  width = Math.max(10, Math.min(width, natural.w))
  height = Math.max(10, Math.min(height, natural.h))
  x = Math.max(0, Math.min(natural.w - width, x))
  y = Math.max(0, Math.min(natural.h - height, y))
  return { x, y, width, height }
}

const mapCropToBase = (rect) => {
  if (!rect) return rect
  const natural = getWorkingNatural()
  return clampCropRect({ ...rect }, natural)
}

const rotateLoading = ref(false)
const applyRotate = async (delta) => {
  if (rotateLoading.value) return
  if (isCropping.value || isScaling.value) {
    ElMessage.warning('请先应用或取消当前操作')
    return
  }
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  rotateLoading.value = true
  const nextDeg = (Number(editParams.value.deg) || 0) + delta
  editParams.value.deg = ((nextDeg % 360) + 360) % 360
  pushHistory()
  await renderPreview()
  ElMessage.success(delta > 0 ? '已顺时针旋转90°' : '已逆时针旋转90°')
  rotateLoading.value = false
}

const resetAdjust = async () => {
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  editParams.value.brightness = 0
  editParams.value.contrast = 0
  editParams.value.saturation = 0
  editParams.value.temperature = 0
  editParams.value.sharpness = 0
  resetPreviewAdjust()
  pushHistory()
  await renderPreview()
  ElMessage.success('已重置调节')
}

const applyAdjust = async () => {
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  const payload = normalizeAdjustValues(previewAdjust)
  const delta = diffAdjustValues(editParams.value, payload)
  if (!hasAdjustDelta(delta)) {
    ElMessage.info('当前没有可应用的调节')
    return
  }
  editParams.value.brightness = payload.brightness
  editParams.value.contrast = payload.contrast
  editParams.value.saturation = payload.saturation
  editParams.value.temperature = payload.temperature
  editParams.value.sharpness = payload.sharpness
  resetPreviewAdjust(editParams.value)
  pushHistory()
  await renderPreview()
  ElMessage.success('已应用调节')
}

const scaleLoading = ref(false)
const startScaleMode = async () => {
  if (isScaling.value) return
  const natural = getWorkingNatural()
  if (!natural.w || !natural.h) {
    ElMessage.warning('无法获取图片尺寸')
    return
  }
  isCropping.value = false
  scaleBase.value = { w: natural.w, h: natural.h }
  scaleRect.value = { width: natural.w, height: natural.h }
  isScaling.value = true
  await nextTick()
  syncImgBox()
}

const cancelScale = async () => {
  if (!isScaling.value) return
  isScaling.value = false
  scaleRect.value = { width: scaleBase.value.w, height: scaleBase.value.h }
  await nextTick()
  syncImgBox()
}

const applyScale = async () => {
  if (!isScaling.value) {
    ElMessage.warning('请先进入缩放模式')
    return
  }
  if (scaleLoading.value) return
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  const base = scaleBase.value
  if (!base.w || !base.h) {
    ElMessage.warning('无法获取图片尺寸')
    return
  }
  const tw = Math.round(scaleRect.value.width || base.w)
  const th = Math.round(scaleRect.value.height || base.h)
  const clamp = (val) => Math.min(MAX_SCALE_PX, Math.max(MIN_SCALE_PX, Math.round(val)))
  const targetW = clamp(tw)
  const targetH = clamp(th)

  if (targetW === base.w && targetH === base.h) {
    isScaling.value = false
    return
  }

  scaleLoading.value = true
  editParams.value.target_width = targetW
  editParams.value.target_height = targetH
  editParams.value.keep_ratio = false
  pushHistory()
  await renderPreview()
  isScaling.value = false
  scaleBase.value = { w: targetW, h: targetH }
  scaleRect.value = { width: targetW, height: targetH }
  ElMessage.success('已应用缩放')
  scaleLoading.value = false
}

function startScaleDrag(evt, handle) {
  if (!isScaling.value || !scaleBase.value.w || !scaleBase.value.h) return
  scaleDragState.value = {
    handle,
    startX: evt.clientX,
    startY: evt.clientY,
    startW: scaleRect.value.width || scaleBase.value.w,
    startH: scaleRect.value.height || scaleBase.value.h,
  }
  window.addEventListener('mousemove', onScaleDrag)
  window.addEventListener('mouseup', endScaleDrag)
}

function onScaleDrag(evt) {
  const st = scaleDragState.value
  if (!st) return
  const base = scaleBase.value
  if (!base.w || !base.h || !renderScale.value) return
  const dx = (evt.clientX - st.startX) / renderScale.value
  const dy = (evt.clientY - st.startY) / renderScale.value
  let nextW = st.startW
  let nextH = st.startH

  const hasX = st.handle.includes('e') || st.handle.includes('w')
  const hasY = st.handle.includes('n') || st.handle.includes('s')
  if (hasX) {
    if (st.handle.includes('e')) nextW = st.startW + dx
    if (st.handle.includes('w')) nextW = st.startW - dx
  }
  if (hasY) {
    if (st.handle.includes('s')) nextH = st.startH + dy
    if (st.handle.includes('n')) nextH = st.startH - dy
  }
  if (hasX && hasY) {
    // 四角：保持比例缩放
    const aspect = st.startW / st.startH || 1
    const deltaW = nextW - st.startW
    const deltaH = nextH - st.startH
    if (Math.abs(deltaW) >= Math.abs(deltaH)) {
      nextH = nextW / aspect
    } else {
      nextW = nextH * aspect
    }
  }

  const clamp = (val) => Math.min(MAX_SCALE_PX, Math.max(MIN_SCALE_PX, val))
  nextW = clamp(nextW)
  nextH = clamp(nextH)
  scaleRect.value = { width: Math.round(nextW), height: Math.round(nextH) }
}

function endScaleDrag() {
  window.removeEventListener('mousemove', onScaleDrag)
  window.removeEventListener('mouseup', endScaleDrag)
  scaleDragState.value = null
}

const cropLoading = ref(false)
const applyCrop = async () => {
  if (!isCropping.value) {
    ElMessage.warning('请先进入裁剪模式并调整裁剪框')
    return
  }
  if (cropLoading.value) return
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  const rect = mapCropToBase(cropRect.value)
  if (!rect?.width || !rect?.height) {
    ElMessage.warning('请先调整裁剪框大小')
    return
  }
  cropLoading.value = true
  editParams.value.crop_rect = { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
  pushHistory()
  await renderPreview()
  isCropping.value = false
  initCropRect()
  ElMessage.success('已应用裁剪')
  cropLoading.value = false
}

const buildRectStyle = (rect) => {
  const natural = getWorkingNatural()
  if (!rect || !imgBox.value.w || !imgBox.value.h || !natural.w || !natural.h) return {}
  const fx = imgBox.value.w / natural.w
  const fy = imgBox.value.h / natural.h
  return {
    left: `${rect.x * fx}px`,
    top: `${rect.y * fy}px`,
    width: `${rect.width * fx}px`,
    height: `${rect.height * fy}px`,
  }
}

const cropRectStyle = computed(() => buildRectStyle(cropRect.value))
const scaleInfo = computed(() => {
  const baseW = scaleBase.value.w || imgNatural.value.w || image.value.width || 0
  const baseH = scaleBase.value.h || imgNatural.value.h || image.value.height || 0
  const w = Math.round(scaleRect.value.width || baseW)
  const h = Math.round(scaleRect.value.height || baseH)
  if (!w || !h) return ''
  return `${w} × ${h}`
})

const startDrag = (evt, mode) => {
  if (!isCropping.value || !imgBox.value.w) return
  dragState.value = {
    mode,
    startX: evt.clientX,
    startY: evt.clientY,
    cropStart: { ...cropRect.value },
  }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', endDrag)
}

const onDrag = (evt) => {
  const st = dragState.value
  if (!st) return
  const dx = evt.clientX - st.startX
  const dy = evt.clientY - st.startY
  const natural = getWorkingNatural()
  const fx = natural.w / imgBox.value.w
  const fy = natural.h / imgBox.value.h
  let { x, y, width, height } = st.cropStart
  const moveX = dx * fx
  const moveY = dy * fy

  const clamp = () => {
    x = Math.max(0, Math.min(natural.w - width, x))
    y = Math.max(0, Math.min(natural.h - height, y))
    width = Math.max(10, Math.min(natural.w - x, width))
    height = Math.max(10, Math.min(natural.h - y, height))
  }

  if (st.mode === 'move') {
    x += moveX
    y += moveY
    clamp()
  } else {
    if (st.mode.includes('e')) width += moveX
    if (st.mode.includes('w')) { x += moveX; width -= moveX }
    if (st.mode.includes('s')) height += moveY
    if (st.mode.includes('n')) { y += moveY; height -= moveY }
    clamp()
  }
  cropRect.value = { x, y, width, height }
}

const endDrag = () => {
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', endDrag)
  dragState.value = null
}

const exportMode = ref('override')
const exportName = ref('')
const skipLeaveConfirm = ref(false)
const onExport = async () => {
  if (exportMode.value === 'new' && !exportName.value.trim()) {
    ElMessage.warning('请先输入导出名称')
    return
  }
  if (previewLoading.value) {
    ElMessage.info('正在生成预览，请稍后')
    return
  }
  if (isCropping.value || isScaling.value) {
    ElMessage.warning('请先应用或取消当前操作')
    return
  }
  if (hasPreviewAdjust.value) {
    ElMessage.warning('请先应用或重置调节')
    return
  }
  try {
    const imageId = image.value.id || route.params.id
    const payload = {
      ...cloneParams(editParams.value),
      mode: exportMode.value,
    }
    const trimmedName = exportName.value.trim()
    if (trimmedName) {
      payload.exportName = trimmedName
    }
    const { data } = await api.post(`/api/images/${imageId}/edit`, payload)
    const nextId = data?.image_id || imageId
    const stamp = data?.updatedAt ? new Date(data.updatedAt).getTime() || Date.now() : Date.now()
    ElMessage.success('导出成功')
    skipLeaveConfirm.value = true
    resetHistory()
    await router.push({ name: 'ImageDetail', params: { id: nextId }, query: buildDetailQuery(stamp) })
  } catch (err) {
    skipLeaveConfirm.value = false
    ElMessage.error(err?.response?.data?.error || '导出失败')
  }
}

const promptCommitMode = async () => {
  const overrideName = exportName.value.trim()
  try {
    await ElMessageBox.confirm('请选择保存方式', '保存图片', {
      confirmButtonText: '覆盖原图',
      cancelButtonText: '导出新图',
      distinguishCancelAndClose: true,
    })
    return { mode: 'override', exportName: overrideName || undefined }
  } catch (action) {
    if (action !== 'cancel') return null
    try {
      const { value } = await ElMessageBox.prompt('请输入导出名称', '导出新图', {
        inputPlaceholder: image.value.title || '未命名',
        inputValidator: (val) => (!!val && !!val.trim()) || '请输入导出名称',
      })
      return { mode: 'new', exportName: value.trim() }
    } catch {
      return null
    }
  }
}

const confirmLeave = async () => {
  if (skipLeaveConfirm.value) return true
  if (isCropping.value || isScaling.value) {
    ElMessage.warning('请先应用或取消当前操作')
    return false
  }
  if (hasPreviewAdjust.value) {
    ElMessage.warning('请先应用或重置调节')
    return false
  }
  const hasEdits = historyIndex.value > 0
  if (!hasEdits) return true
  try {
    await ElMessageBox.confirm('是否保存修改后的图片', '是否保存修改后的图片', {
      confirmButtonText: '保存',
      cancelButtonText: '不保存',
      type: 'warning',
      distinguishCancelAndClose: true,
    })
    const commitPayload = await promptCommitMode()
    if (!commitPayload) return false
    const imageId = image.value.id || route.params.id
    const payload = {
      ...cloneParams(editParams.value),
      mode: commitPayload.mode,
    }
    if (commitPayload.exportName) {
      payload.exportName = commitPayload.exportName
    }
    await api.post(`/api/images/${imageId}/edit`, payload)
    return true
  } catch (action) {
    if (action === 'cancel') {
      return true
    }
    return false
  }
}

const goBack = () => {
  router.push({
    name: 'ImageDetail',
    params: { id: image.value.id || route.params.id },
    query: buildDetailQuery(),
  })
}

onBeforeRouteLeave(async () => {
  const ok = await confirmLeave()
  if (!ok) return false
})
</script>

<template>
  <div class="editor-page">
    <header class="editor-top">
      <el-button text class="back-btn" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </el-button>
      <span class="title">图片编辑 · {{ image.title || '未命名' }}</span>
      <el-tag v-if="previewLoading" size="small" type="warning" effect="plain">正在生成预览...</el-tag>
      <el-tag v-else size="small" type="success" effect="plain">编辑已就绪</el-tag>
    </header>

    <section class="editor-layout">
      <div class="editor-left">
        <div class="stage-shell">
          <div class="stage">
            <div class="stage-toolbar">
              <div class="stage-toolbar-left">
                <el-button text :icon="ZoomOut" @click="changeZoom(-10)" />
                <span class="zoom-text">{{ zoom }}%</span>
                <el-button text :icon="ZoomIn" @click="changeZoom(10)" />
                <el-button text :icon="FullScreen" @click="fitScreen">适应屏幕</el-button>
              </div>
              <div class="stage-toolbar-right">
                <el-tooltip :content="canUndo ? '撤回上一步' : '暂无可撤回操作'" placement="top">
                  <span>
                    <el-button text :icon="RefreshLeft" :disabled="!canUndo" @click="undo" />
                  </span>
                </el-tooltip>
                <el-tooltip :content="canRedo ? '重做一步' : '暂无可重做操作'" placement="top">
                  <span>
                    <el-button text :icon="RefreshRight" :disabled="!canRedo" @click="redo" />
                  </span>
                </el-tooltip>
              </div>
            </div>
            <div class="stage-body">
              <el-skeleton v-if="loading" :rows="6" animated style="width:100%;height:360px;" />
              <div v-else ref="stageRef" class="stage-area">
                <div v-if="previewUrl && !loadError" class="img-holder" :style="holderStyle">
                  <img
                    ref="imgEl"
                    :key="previewKey"
                    :src="previewUrl"
                    :alt="image.title"
                    :style="imgStyle"
                    @load="onEditorImgLoad"
                    @error="onImgError"
                  />
                  <div v-if="isCropping" class="crop-overlay">
                    <div class="crop-mask"></div>
                    <div class="crop-rect" :style="cropRectStyle" @mousedown.prevent="startDrag($event, 'move')">
                      <span class="handle handle-nw" @mousedown.stop.prevent="startDrag($event, 'nw')"></span>
                      <span class="handle handle-ne" @mousedown.stop.prevent="startDrag($event, 'ne')"></span>
                      <span class="handle handle-sw" @mousedown.stop.prevent="startDrag($event, 'sw')"></span>
                      <span class="handle handle-se" @mousedown.stop.prevent="startDrag($event, 'se')"></span>
                    </div>
                  </div>
                  <div v-if="isScaling" class="scale-overlay">
                    <div class="scale-rect">
                      <span class="handle handle-nw" @mousedown.stop.prevent="startScaleDrag($event, 'nw')"></span>
                      <span class="handle handle-ne" @mousedown.stop.prevent="startScaleDrag($event, 'ne')"></span>
                      <span class="handle handle-sw" @mousedown.stop.prevent="startScaleDrag($event, 'sw')"></span>
                      <span class="handle handle-se" @mousedown.stop.prevent="startScaleDrag($event, 'se')"></span>
                      <span class="handle handle-n" @mousedown.stop.prevent="startScaleDrag($event, 'n')"></span>
                      <span class="handle handle-s" @mousedown.stop.prevent="startScaleDrag($event, 's')"></span>
                      <span class="handle handle-e" @mousedown.stop.prevent="startScaleDrag($event, 'e')"></span>
                      <span class="handle handle-w" @mousedown.stop.prevent="startScaleDrag($event, 'w')"></span>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-preview">
                  <p>{{ loadError || '暂无图片' }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="editor-right">
        <el-scrollbar class="right-scroll">
          <div class="panel neutral">
            <div class="panel-title">裁剪</div>
            <div class="ratio-row crop-actions">
              <el-button size="small" :type="isCropping ? 'primary' : 'default'" :disabled="isCropping" @click="toggleCropMode">裁剪</el-button>
              <el-button size="small" type="primary" @click="applyCrop" :disabled="!isCropping || previewLoading" :loading="cropLoading">应用裁剪</el-button>
              <el-button size="small" @click="cancelCrop" :disabled="!isCropping">取消裁剪</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">缩放</div>
            <div class="ratio-row scale-actions">
              <el-button size="small" :type="isScaling ? 'primary' : 'default'" :disabled="isScaling" @click="startScaleMode">缩放</el-button>
              <el-button size="small" type="primary" :loading="scaleLoading" :disabled="!isScaling || previewLoading" @click="applyScale">应用缩放</el-button>
              <el-button size="small" :disabled="!isScaling" @click="cancelScale">取消缩放</el-button>
            </div>
            <div v-if="isScaling && scaleInfo" class="scale-info">目标尺寸：{{ scaleInfo }} px</div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">旋转</div>
            <div class="rotate-row">
              <el-button size="small" :loading="rotateLoading" @click="applyRotate(-90)">-90°</el-button>
              <el-button size="small" :loading="rotateLoading" @click="applyRotate(90)">+90°</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">调节</div>
            <div class="slider-row">
              <span>亮度</span>
              <el-slider v-model="previewAdjust.brightness" :min="-100" :max="100" />
            </div>
            <div class="slider-row">
              <span>对比度</span>
              <el-slider v-model="previewAdjust.contrast" :min="-100" :max="100" />
            </div>
            <div class="slider-row">
              <span>饱和度</span>
              <el-slider v-model="previewAdjust.saturation" :min="-100" :max="100" />
            </div>
            <div class="slider-row">
              <span>色温</span>
              <el-slider v-model="previewAdjust.temperature" :min="-100" :max="100" :step="1" show-input />
            </div>
            <div class="slider-row">
              <span>锐化</span>
              <el-slider v-model="previewAdjust.sharpness" :min="0" :max="100" :step="1" show-input />
            </div>
            <div class="adjust-hint">调节会生成预览，应用后保存</div>
            <div class="slider-row reset-row">
              <el-button size="small" type="primary" :disabled="previewLoading" @click="applyAdjust">应用调节</el-button>
              <el-button size="small" @click="resetAdjust">重置所有调节</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">导出 / 版本</div>
            <div class="export-row">
              <el-radio-group v-model="exportMode">
                <el-radio label="override">覆盖原图</el-radio>
                <el-radio label="new">导出为新图片</el-radio>
              </el-radio-group>
            </div>
            <div class="export-name">
              <span class="export-label">导出名称：</span>
              <el-input v-model="exportName" placeholder="请输入导出图片名称" size="small" />
              <div class="export-tip">
                {{ exportMode === 'override' ? '覆盖时会以此名称更新原图标题' : '为新图片命名后再导出' }}
              </div>
            </div>
            <div class="export-actions">
              <el-button type="primary" @click="onExport">导出并保存</el-button>
            </div>
            <div class="export-note">
              <p>提示：未来可用“新建+删除原图”方式实现覆盖。</p>
            </div>
          </div>
        </el-scrollbar>
      </div>
    </section>
  </div>
</template>

<style scoped>
.editor-page {
  --header-h: 64px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #f5f7fa;
}
.editor-top {
  height: var(--header-h);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.editor-top .title {
  font-weight: 700;
  color: #1f2937;
}
.editor-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  padding: 16px;
}
.editor-left {
  min-width: 0;
  min-height: 0;
  display: flex;
}
.stage-shell {
  flex: 1;
  min-width: 0;
  display: flex;
  justify-content: center;
}
.stage {
  width: 100%;
  max-width: 980px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.stage-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.stage-toolbar-left,
.stage-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.zoom-text {
  width: 56px;
  text-align: center;
  color: #374151;
}
.stage-body {
  flex: 1;
  min-height: 0;
  background: linear-gradient(135deg, #eef2f7, #e5e7eb);
  border-radius: 10px;
  padding: 16px;
  overflow: hidden;
}
.stage-area {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
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
.empty-preview {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #9ca3af;
  font-size: 14px;
}
.crop-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.crop-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  pointer-events: none;
}
.crop-rect {
  position: absolute;
  border: 2px solid #1f6feb;
  border-radius: 4px;
  box-sizing: border-box;
  pointer-events: auto;
}
.crop-rect .handle,
.scale-rect .handle {
  position: absolute;
  width: 12px;
  height: 12px;
  background: #1f6feb;
  border: 2px solid #fff;
  border-radius: 50%;
  pointer-events: auto;
}
.scale-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.scale-rect {
  position: absolute;
  inset: 0;
  border: 2px dashed #1f6feb;
  border-radius: 4px;
  box-sizing: border-box;
  pointer-events: auto;
}
.handle-nw { top: -6px; left: -6px; cursor: nwse-resize; }
.handle-ne { top: -6px; right: -6px; cursor: nesw-resize; }
.handle-sw { bottom: -6px; left: -6px; cursor: nesw-resize; }
.handle-se { bottom: -6px; right: -6px; cursor: nwse-resize; }
.handle-n { top: -6px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
.handle-s { bottom: -6px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
.handle-e { right: -6px; top: 50%; transform: translateY(-50%); cursor: ew-resize; }
.handle-w { left: -6px; top: 50%; transform: translateY(-50%); cursor: ew-resize; }

.editor-right {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.right-scroll {
  height: 100%;
  padding-right: 8px;
}
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
}
.panel + .panel {
  margin-top: 12px;
}
.panel-title {
  font-weight: 600;
  color: #1f6feb;
  margin-bottom: 8px;
}
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
.adjust-hint {
  padding-left: 60px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}
.scale-info {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}
.reset-row {
  justify-content: flex-end;
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

@media (max-width: 1100px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }
  .editor-right {
    height: auto;
  }
}

@media (max-width: 768px) {
  .editor-page {
    height: auto;
    min-height: 100vh;
    overflow-y: auto;
  }

  .editor-top {
    flex-wrap: wrap;
    gap: 8px;
  }

  .editor-top .title {
    white-space: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .stage-body {
    height: clamp(240px, 50vh, 560px);
  }
}
</style>
