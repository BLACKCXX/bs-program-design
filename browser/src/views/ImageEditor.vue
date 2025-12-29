<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ZoomOut, ZoomIn, FullScreen } from '@element-plus/icons-vue'
import api from '../api/http'

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
const workingImageId = ref(null)
const workingUrl = ref('')
const previewUrl = ref('')
const previewKey = computed(() => `${previewUrl.value || 'empty'}`)
const loading = ref(false)
const previewLoading = ref(false)
const ready = ref(false)
const loadError = ref('')
const blobUrl = ref('')
const previewObjectUrl = ref('')
const checkpointUrl = ref('')

const zoom = ref(100)
const changeZoom = (delta) => {
  zoom.value = Math.min(200, Math.max(33, zoom.value + delta))
}
const fitScreen = () => {
  zoom.value = 100
}

const normalizeFilePath = (p = '') => {
  if (!p) return ''
  let clean = String(p).replace(/\\/g, '/').replace(/^\/+/, '')
  clean = clean.replace(/^files\//, '')
  return `/files/${encodeURI(clean)}`
}

const buildVersionedUrl = (rawUrl, stamp = Date.now()) => {
  if (!rawUrl) return ''
  return `${normalizeFilePath(rawUrl)}?v=${stamp}`
}

const pickUrl = (data = {}) =>
  data.url ||
  data.cover_url ||
  data.thumb_url ||
  data.stored_path ||
  data.path ||
  data.thumb ||
  ''

const fetchPreviewBlob = async (url, asBase = false) => {
  try {
    const resp = await api.get(url, { responseType: 'blob' })
    if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = URL.createObjectURL(resp.data)
    previewUrl.value = blobUrl.value
    if (asBase) {
      workingUrl.value = blobUrl.value
    }
  } catch (err) {
    console.error('[editor] blob fetch failed', url, err)
    ElMessage.error('图片加载失败')
  }
}

const onImgError = async (e) => {
  const badUrl = e?.target?.src
  console.error('[editor] load error', badUrl)
  if (badUrl && badUrl.startsWith('blob:')) return
  const fallbackUrl = workingUrl.value || image.value.url
  if (fallbackUrl) {
    await fetchPreviewBlob(fallbackUrl, true)
  }
}

const getFromQuery = () => (typeof route.query.from === 'string' ? route.query.from : '')
const buildDetailQuery = (stamp = Date.now()) => {
  const query = { t: stamp }
  const from = getFromQuery()
  if (from) query.from = from
  return query
}

const loadDetail = async () => {
  try {
    loading.value = true
    ready.value = false
    loadError.value = ''
    previewUrl.value = ''
    previewSeq += 1
    endScaleDrag()
    const { data } = await api.get(`/api/images/${route.params.id}`)
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
    workingImageId.value = data?.id || route.params.id
    workingUrl.value = absUrl
    previewUrl.value = absUrl
    checkpointUrl.value = absUrl
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = ''
    }
    if (previewObjectUrl.value) {
      URL.revokeObjectURL(previewObjectUrl.value)
      previewObjectUrl.value = ''
    }
    imgNatural.value = { w: 0, h: 0 }
    cropRect.value = { x: 0, y: 0, width: 0, height: 0 }
    isCropping.value = false
    isScaling.value = false
    scaleRect.value = { width: 0, height: 0 }
    scaleBase.value = { w: 0, h: 0 }
    zoom.value = 100
    brightness.value = 0
    contrast.value = 0
    saturation.value = 0
    warmth.value = 0
    sharpen.value = 0
    history.value = []
    exportName.value = image.value.title || ''
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '加载图片详情失败')
    loadError.value = err?.response?.data?.error || err?.message || '加载失败'
  }
  loading.value = false
  ready.value = true
}

// ---- 编辑状态 ----
const isCropping = ref(false)
const cropRect = ref({ x: 0, y: 0, width: 0, height: 0 })
const dragState = ref(null)
const history = ref([])

const brightness = ref(0)
const contrast = ref(0)
const saturation = ref(0)
const warmth = ref(0)
const sharpen = ref(0)

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
let previewTimer = null
let previewSeq = 0

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
  return Math.min(w / bw, h / bh) * 0.98
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

onUnmounted(() => {
  endScaleDrag()
  if (stageObserver) {
    stageObserver.disconnect()
    stageObserver = null
  }
  if (previewTimer) {
    clearTimeout(previewTimer)
    previewTimer = null
  }
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
  if (previewObjectUrl.value) {
    URL.revokeObjectURL(previewObjectUrl.value)
    previewObjectUrl.value = ''
  }
})

watch(
  () => route.params.id,
  () => {
    loadDetail()
  },
  { immediate: true }
)

const clearPreviewObjectUrl = () => {
  if (previewObjectUrl.value) {
    URL.revokeObjectURL(previewObjectUrl.value)
    previewObjectUrl.value = ''
  }
}

const resetPreviewToBase = () => {
  clearPreviewObjectUrl()
  if (workingUrl.value) {
    previewUrl.value = workingUrl.value
  }
}

// 进入裁剪/缩放模式时保存当前工作图，取消时可回滚
const saveCheckpoint = () => {
  checkpointUrl.value = workingUrl.value
}
const restoreCheckpoint = () => {
  if (checkpointUrl.value && checkpointUrl.value !== workingUrl.value) {
    workingUrl.value = checkpointUrl.value
    previewUrl.value = checkpointUrl.value
    clearPreviewObjectUrl()
  }
}

const buildPreviewPayload = () => ({
  brightness: brightness.value,
  contrast: contrast.value,
  saturation: saturation.value,
  warmth: warmth.value,
  sharpen: sharpen.value,
})

const hasPreviewEdits = (payload) => {
  const hasAdjust =
    Number(payload.brightness) ||
    Number(payload.contrast) ||
    Number(payload.saturation) ||
    Number(payload.warmth) ||
    Number(payload.sharpen)
  return !!hasAdjust
}

const schedulePreview = () => {
  if (!ready.value) return
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => refreshPreview(), 260)
}

const refreshPreview = async () => {
  const targetId = workingImageId.value || image.value.id || route.params.id
  if (!ready.value || !targetId) return
  const payload = buildPreviewPayload()
  if (!hasPreviewEdits(payload)) {
    resetPreviewToBase()
    return
  }
  previewLoading.value = true
  const seq = ++previewSeq
  try {
    const { data } = await api.post(`/api/images/${targetId}/preview`, payload, { responseType: 'blob' })
    if (seq !== previewSeq) return
    clearPreviewObjectUrl()
    previewObjectUrl.value = URL.createObjectURL(data)
    previewUrl.value = previewObjectUrl.value
  } catch (err) {
    console.error('[editor] preview failed', err)
    ElMessage.error(err?.response?.data?.error || '预览生成失败')
  } finally {
    if (seq === previewSeq) {
      previewLoading.value = false
    }
  }
}

const applyEditAndSync = async (payload) => {
  const targetId = workingImageId.value || image.value.id || route.params.id
  const { data } = await api.post(`/api/images/${targetId}/edit`, payload)
  const nextId = data?.image_id || targetId
  const stamp = data?.updatedAt ? new Date(data.updatedAt).getTime() || Date.now() : Date.now()
  const nextUrl = data?.url ? buildVersionedUrl(data.url, stamp) : workingUrl.value

  workingImageId.value = nextId
  image.value.id = nextId
  if (nextUrl) {
    workingUrl.value = nextUrl
    previewUrl.value = nextUrl
    image.value.url = nextUrl
  }
  checkpointUrl.value = workingUrl.value
  previewSeq += 1
  clearPreviewObjectUrl()
  imgNatural.value = { w: 0, h: 0 }
  await nextTick()
  updateStageSize()
  syncImgBox()
  return { nextId, stamp, nextUrl, mode: data?.mode }
}

watch([brightness, contrast, saturation, warmth, sharpen], () => {
  if (!ready.value) return
  schedulePreview()
})

const captureSnapshot = () => {
  history.value.push({
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    cropRect: cropRect.value ? { ...cropRect.value } : null,
    isScaling: isScaling.value,
    scaleRect: scaleRect.value ? { ...scaleRect.value } : null,
    scaleBase: scaleBase.value ? { ...scaleBase.value } : null,
  })
}

const undo = () => {
  const prev = history.value.pop()
  if (!prev) return
  brightness.value = prev.brightness
  contrast.value = prev.contrast
  saturation.value = prev.saturation
  warmth.value = prev.warmth
  sharpen.value = prev.sharpen
  cropRect.value = prev.cropRect ? { ...prev.cropRect } : { ...cropRect.value }
  isScaling.value = prev.isScaling ?? false
  scaleRect.value = prev.scaleRect ? { ...prev.scaleRect } : { ...scaleRect.value }
  scaleBase.value = prev.scaleBase ? { ...prev.scaleBase } : { ...scaleBase.value }
  isCropping.value = false
  refreshPreview()
}

const toggleCropMode = () => {
  if (!isCropping.value) {
    saveCheckpoint()
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
  restoreCheckpoint()
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
  rotateLoading.value = true
  try {
    // 旋转为像素级更新，避免后续操作回到原图
    await applyEditAndSync({ mode: 'override', rotate: delta })
    ElMessage.success(delta > 0 ? '已顺时针旋转90°' : '已逆时针旋转90°')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '旋转失败')
  } finally {
    rotateLoading.value = false
  }
}

const resetAdjust = async () => {
  captureSnapshot()
  brightness.value = 0
  contrast.value = 0
  saturation.value = 0
  warmth.value = 0
  sharpen.value = 0
  isCropping.value = false
  isScaling.value = false
  scaleRect.value = { width: 0, height: 0 }
  scaleBase.value = { w: 0, h: 0 }
  initCropRect()
  await refreshPreview()
}

const scaleLoading = ref(false)
const startScaleMode = async () => {
  if (isScaling.value) return
  const natural = getWorkingNatural()
  if (!natural.w || !natural.h) {
    ElMessage.warning('无法获取图片尺寸')
    return
  }
  saveCheckpoint()
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
  restoreCheckpoint()
}

const applyScale = async () => {
  if (!isScaling.value) {
    ElMessage.warning('请先进入缩放模式')
    return
  }
  if (scaleLoading.value) return
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
  try {
    captureSnapshot()
    const payload = {
      mode: 'override',
      // 后端 Pillow 使用 LANCZOS 重采样，确保像素级缩放（stretch）
      target_width: targetW,
      target_height: targetH,
      keep_ratio: false,
      resize_mode: 'stretch',
    }
    await applyEditAndSync(payload)
    image.value.width = targetW
    image.value.height = targetH
    isScaling.value = false
    scaleBase.value = { w: targetW, h: targetH }
    scaleRect.value = { width: targetW, height: targetH }
    await refreshPreview()
    ElMessage.success('已应用缩放')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '缩放失败')
  } finally {
    scaleLoading.value = false
  }
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
  const rect = mapCropToBase(cropRect.value)
  if (!rect?.width || !rect?.height) {
    ElMessage.warning('请先调整裁剪框大小')
    return
  }
  cropLoading.value = true
  try {
    captureSnapshot()
    const payload = {
      mode: 'override',
      crop_rect: rect,
    }
    await applyEditAndSync(payload)
    image.value.width = Math.round(rect.width)
    image.value.height = Math.round(rect.height)
    isCropping.value = false
    initCropRect()
    await refreshPreview()
    ElMessage.success('已应用裁剪')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '裁剪失败')
  } finally {
    cropLoading.value = false
  }
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
const onExport = async () => {
  if (exportMode.value === 'new' && !exportName.value.trim()) {
    ElMessage.warning('请先输入导出名称')
    return
  }
  const cropPayload = isCropping.value ? mapCropToBase(cropRect.value) : null
  const payload = {
    mode: exportMode.value,
    exportName: exportName.value || image.value.title,
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    crop_rect: cropPayload,
  }
  try {
    const targetId = workingImageId.value || image.value.id || route.params.id
    const { data } = await api.post(`/api/images/${targetId}/edit`, payload)
    const nextId = data?.image_id || targetId
    const stamp = data?.updatedAt ? new Date(data.updatedAt).getTime() || Date.now() : Date.now()
    ElMessage.success('导出成功')
    router.push({ name: 'ImageDetail', params: { id: nextId }, query: buildDetailQuery(stamp) })
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '导出失败')
  }
}

const goBack = () => {
  router.push({
    name: 'ImageDetail',
    params: { id: workingImageId.value || route.params.id },
    query: buildDetailQuery(),
  })
}
</script>

<template>
  <div class="editor-page">
    <header class="editor-top">
      <el-button text class="back-btn" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </el-button>
      <span class="title">图片编辑 · {{ image.title || '未命名' }}</span>
    </header>

    <section class="editor-layout">
      <div class="editor-left">
        <div class="stage-shell">
          <div class="stage">
            <div class="stage-toolbar">
              <el-button text :icon="ZoomOut" @click="changeZoom(-10)" />
              <span class="zoom-text">{{ zoom }}%</span>
              <el-button text :icon="ZoomIn" @click="changeZoom(10)" />
              <el-button text :icon="FullScreen" @click="fitScreen">适应屏幕</el-button>
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
              <el-button size="small" type="primary" @click="applyCrop" :disabled="!isCropping" :loading="cropLoading">应用裁剪</el-button>
              <el-button size="small" @click="cancelCrop" :disabled="!isCropping">取消裁剪</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">缩放</div>
            <div class="ratio-row scale-actions">
              <el-button size="small" :type="isScaling ? 'primary' : 'default'" :disabled="isScaling" @click="startScaleMode">缩放</el-button>
              <el-button size="small" type="primary" :loading="scaleLoading" :disabled="!isScaling" @click="applyScale">应用缩放</el-button>
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
              <el-slider v-model="brightness" :min="-100" :max="100" @change="captureSnapshot" />
            </div>
            <div class="slider-row">
              <span>对比度</span>
              <el-slider v-model="contrast" :min="-100" :max="100" @change="captureSnapshot" />
            </div>
            <div class="slider-row">
              <span>饱和度</span>
              <el-slider v-model="saturation" :min="-100" :max="100" @change="captureSnapshot" />
            </div>
            <div class="slider-row">
              <span>色温</span>
              <el-slider v-model="warmth" :min="-100" :max="100" :step="1" show-input @change="captureSnapshot" />
            </div>
            <div class="slider-row">
              <span>锐化</span>
              <el-slider v-model="sharpen" :min="0" :max="100" :step="1" show-input @change="captureSnapshot" />
            </div>
            <div class="slider-row reset-row">
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
  gap: 8px;
  margin-bottom: 10px;
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
</style>
