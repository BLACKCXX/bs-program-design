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
const baseSrc = ref('')
const workingPreviewUrl = ref('')
const previewKey = computed(() => `${workingPreviewUrl.value || 'empty'}`)
const loading = ref(false)
const previewLoading = ref(false)
const ready = ref(false)
const loadError = ref('')
const blobUrl = ref('')
const previewObjectUrl = ref('')

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
    workingPreviewUrl.value = blobUrl.value
    if (asBase) {
      baseSrc.value = blobUrl.value
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
  if (image.value.url) {
    await fetchPreviewBlob(image.value.url, true)
  }
}

const loadDetail = async () => {
  try {
    loading.value = true
    ready.value = false
    loadError.value = ''
    workingPreviewUrl.value = ''
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
    baseSrc.value = absUrl
    workingPreviewUrl.value = absUrl
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = ''
    }
    if (previewObjectUrl.value) {
      URL.revokeObjectURL(previewObjectUrl.value)
      previewObjectUrl.value = ''
    }
    imgNatural.value = { w: 0, h: 0 }
    pendingCrop.value = null
    isCropping.value = false
    targetWidth.value = null
    targetHeight.value = null
    cropAspect.value = 'free'
    customCropW.value = 1
    customCropH.value = 1
    zoom.value = 100
    rotate.value = 0
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
const cropAspect = ref('free')
const customCropW = ref(1)
const customCropH = ref(1)
const cropRect = ref({ x: 0, y: 0, width: 0, height: 0 })
const pendingCrop = ref(null)
const dragState = ref(null)
const history = ref([])

const ROTATE_MIN = -180
const ROTATE_MAX = 180
const rotate = ref(0)

const brightness = ref(0)
const contrast = ref(0)
const saturation = ref(0)
const warmth = ref(0)
const sharpen = ref(0)

const lockRatio = ref(true)
const targetWidth = ref(null)
const targetHeight = ref(null)

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
const holderStyle = computed(() => {
  if (!bboxSize.value.w || !bboxSize.value.h) return {}
  return {
    width: `${bboxSize.value.w * renderScale.value}px`,
    height: `${bboxSize.value.h * renderScale.value}px`,
  }
})
const imgStyle = computed(() => ({
  width: imgNatural.value.w ? `${imgNatural.value.w}px` : undefined,
  height: imgNatural.value.h ? `${imgNatural.value.h}px` : undefined,
  transform: `translate(-50%, -50%) scale(${renderScale.value})`,
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

const onEditorImgLoad = async (e) => {
  const el = e.target
  imgNatural.value = { w: el.naturalWidth, h: el.naturalHeight }
  await nextTick()
  updateStageSize()
  syncImgBox()
}

watch(zoom, async () => {
  await nextTick()
  syncImgBox()
})

watch(isCropping, async () => {
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
  if (baseSrc.value) {
    workingPreviewUrl.value = baseSrc.value
  }
}

const parseAspectValue = (val) => {
  if (!val || val === 'free') return { w: null, h: null }
  const parts = String(val).split(':')
  if (parts.length !== 2) return { w: null, h: null }
  const w = Number(parts[0]) || null
  const h = Number(parts[1]) || null
  return w && h ? { w, h } : { w: null, h: null }
}

const buildPreviewPayload = (options = {}) => {
  const payload = {
    rotate: rotate.value,
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    crop_rect: pendingCrop.value ? { ...pendingCrop.value } : null,
    target_width: targetWidth.value,
    target_height: targetHeight.value,
    keep_ratio: lockRatio.value,
    resize_mode: 'stretch',
  }
  if (options.skipCrop) {
    payload.crop_rect = null
  }
  if (options.skipResize) {
    payload.target_width = null
    payload.target_height = null
  }
  return payload
}

const hasPreviewEdits = (payload) => {
  const rotateVal = Number(payload.rotate) || 0
  const hasAdjust =
    Number(payload.brightness) ||
    Number(payload.contrast) ||
    Number(payload.saturation) ||
    Number(payload.warmth) ||
    Number(payload.sharpen)
  return (
    rotateVal % 360 !== 0 ||
    hasAdjust ||
    !!payload.crop_rect ||
    !!payload.target_width ||
    !!payload.target_height
  )
}

const schedulePreview = (options = {}) => {
  if (!ready.value) return
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => refreshPreview(options), 260)
}

const refreshPreview = async (options = {}) => {
  if (!ready.value || !image.value.id) return
  const skipCrop = options.skipCrop ?? isCropping.value
  const skipResize = options.skipResize ?? isCropping.value
  const payload = buildPreviewPayload({ skipCrop, skipResize })
  if (!hasPreviewEdits(payload)) {
    resetPreviewToBase()
    return
  }
  previewLoading.value = true
  const seq = ++previewSeq
  try {
    const { data } = await api.post(`/api/images/${image.value.id}/preview`, payload, { responseType: 'blob' })
    if (seq !== previewSeq) return
    clearPreviewObjectUrl()
    previewObjectUrl.value = URL.createObjectURL(data)
    workingPreviewUrl.value = previewObjectUrl.value
  } catch (err) {
    console.error('[editor] preview failed', err)
    ElMessage.error(err?.response?.data?.error || '预览生成失败')
  } finally {
    if (seq === previewSeq) {
      previewLoading.value = false
    }
  }
}

watch([rotate, brightness, contrast, saturation, warmth, sharpen], () => {
  if (!ready.value) return
  schedulePreview()
})

const captureSnapshot = () => {
  history.value.push({
    cropAspect: cropAspect.value,
    customCropW: customCropW.value,
    customCropH: customCropH.value,
    rotate: rotate.value,
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    pendingCrop: pendingCrop.value ? { ...pendingCrop.value } : null,
    cropRect: cropRect.value ? { ...cropRect.value } : null,
    lockRatio: lockRatio.value,
    targetWidth: targetWidth.value,
    targetHeight: targetHeight.value,
  })
}

const undo = () => {
  const prev = history.value.pop()
  if (!prev) return
  cropAspect.value = prev.cropAspect
  customCropW.value = prev.customCropW
  customCropH.value = prev.customCropH
  rotate.value = prev.rotate
  brightness.value = prev.brightness
  contrast.value = prev.contrast
  saturation.value = prev.saturation
  warmth.value = prev.warmth
  sharpen.value = prev.sharpen
  pendingCrop.value = prev.pendingCrop ? { ...prev.pendingCrop } : null
  cropRect.value = prev.cropRect ? { ...prev.cropRect } : { ...cropRect.value }
  lockRatio.value = prev.lockRatio
  targetWidth.value = prev.targetWidth
  targetHeight.value = prev.targetHeight
  isCropping.value = false
  refreshPreview()
}

const toggleCropMode = async () => {
  if (!isCropping.value) {
    isCropping.value = true
    if (pendingCrop.value) {
      cropRect.value = { ...pendingCrop.value }
    } else {
      cropRect.value = { x: 0, y: 0, width: 0, height: 0 }
    }
    await refreshPreview({ skipCrop: true, skipResize: true })
    if (!cropRect.value?.width || !cropRect.value?.height) {
      initCropRect()
    }
    return
  }
  isCropping.value = false
  await refreshPreview()
}

const cancelCrop = async () => {
  isCropping.value = false
  if (pendingCrop.value) {
    cropRect.value = { ...pendingCrop.value }
  } else {
    initCropRect()
  }
  await refreshPreview()
}

const getCropRatio = () => {
  const ratio = parseAspectValue(cropAspect.value)
  return ratio.w && ratio.h ? ratio.w / ratio.h : null
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

const applyAspectToRect = (rect, ratio) => {
  if (!rect || !ratio) return rect
  const natural = getWorkingNatural()
  let width = rect.width
  let height = rect.height
  const centerX = rect.x + width / 2
  const centerY = rect.y + height / 2
  if (width / height > ratio) {
    width = height * ratio
  } else {
    height = width / ratio
  }
  const x = centerX - width / 2
  const y = centerY - height / 2
  return clampCropRect({ x, y, width, height }, natural)
}

const setCropAspect = (val) => {
  captureSnapshot()
  cropAspect.value = val
  const ratio = getCropRatio()
  if (isCropping.value && ratio && cropRect.value?.width && cropRect.value?.height) {
    cropRect.value = applyAspectToRect(cropRect.value, ratio)
  }
}
const setCustomCropAspect = () => {
  if (customCropW.value > 0 && customCropH.value > 0) {
    setCropAspect(`${customCropW.value}:${customCropH.value}`)
  }
}

const rotateStep = (delta) => {
  captureSnapshot()
  let next = rotate.value + delta
  if (next > ROTATE_MAX) next -= 360
  if (next < ROTATE_MIN) next += 360
  rotate.value = next
}
const rotateSliderChange = (val) => {
  captureSnapshot()
  rotate.value = val
}

const resetAdjust = () => {
  captureSnapshot()
  brightness.value = 0
  contrast.value = 0
  saturation.value = 0
  warmth.value = 0
  sharpen.value = 0
  schedulePreview()
}

const applySize = async () => {
  captureSnapshot()
  const base = getWorkingNatural()
  if (!base.w || !base.h) {
    ElMessage.warning('无法获取图片尺寸')
    return
  }

  let tw = targetWidth.value ? Number(targetWidth.value) : null
  let th = targetHeight.value ? Number(targetHeight.value) : null
  if (!tw && !th) {
    ElMessage.warning('请输入目标尺寸')
    return
  }

  if (lockRatio.value) {
    if (tw && !th) th = Math.round((tw / base.w) * base.h)
    if (th && !tw) tw = Math.round((th / base.h) * base.w)
    if (tw && th) th = Math.round((tw / base.w) * base.h)
  } else {
    if (tw && !th) th = base.h
    if (th && !tw) tw = base.w
  }

  targetWidth.value = tw
  targetHeight.value = th
  await refreshPreview()
  ElMessage.success('尺寸已应用')
}

const cropLoading = ref(false)
const applyCrop = async () => {
  if (!isCropping.value) {
    ElMessage.warning('请先进入裁剪模式并调整裁剪框')
    return
  }
  if (cropLoading.value) return
  cropLoading.value = true
  try {
    captureSnapshot()
    pendingCrop.value = { ...cropRect.value }
    isCropping.value = false
    await refreshPreview()
    ElMessage.success('已应用裁剪')
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
  const cropPayload = pendingCrop.value ? { ...pendingCrop.value } : (isCropping.value ? { ...cropRect.value } : null)
  const payload = {
    mode: exportMode.value,
    exportName: exportName.value || image.value.title,
    rotate: rotate.value,
    crop_ratio: cropAspect.value,
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    crop_rect: cropPayload,
    target_width: targetWidth.value,
    target_height: targetHeight.value,
    keep_ratio: lockRatio.value,
    resize_mode: 'stretch',
  }
  try {
    const { data } = await api.post(`/api/images/${image.value.id || route.params.id}/edit`, payload)
    const targetId = data?.image_id || image.value.id || route.params.id
    const stamp = data?.updatedAt ? new Date(data.updatedAt).getTime() || Date.now() : Date.now()
    ElMessage.success('导出成功')
    router.push({ name: 'ImageDetail', params: { id: targetId }, query: { t: stamp } })
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '导出失败')
  }
}

const goBack = () => {
  router.push({ name: 'ImageDetail', params: { id: route.params.id } })
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
                <div v-if="workingPreviewUrl && !loadError" class="img-holder" :style="holderStyle">
                  <img
                    ref="imgEl"
                    :key="previewKey"
                    :src="workingPreviewUrl"
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
            <div class="ratio-row">
              <el-button-group>
                <el-button :type="cropAspect === 'free' ? 'primary' : 'default'" @click="setCropAspect('free')">自由</el-button>
                <el-button :type="cropAspect === '1:2' ? 'primary' : 'default'" @click="setCropAspect('1:2')">1:2</el-button>
                <el-button :type="cropAspect === '3:4' ? 'primary' : 'default'" @click="setCropAspect('3:4')">3:4</el-button>
                <el-button :type="cropAspect === '2:1' ? 'primary' : 'default'" @click="setCropAspect('2:1')">2:1</el-button>
                <el-button :type="cropAspect === '1:1' ? 'primary' : 'default'" @click="setCropAspect('1:1')">1:1</el-button>
                <el-button :type="cropAspect === '4:3' ? 'primary' : 'default'" @click="setCropAspect('4:3')">4:3</el-button>
                <el-button :type="cropAspect === '16:9' ? 'primary' : 'default'" @click="setCropAspect('16:9')">16:9</el-button>
              </el-button-group>
              <div class="custom-ratio">
                <span class="custom-label">自定义：</span>
                <el-input-number v-model="customCropW" size="small" :min="1" @change="setCustomCropAspect" controls-position="right" />
                <span class="colon">:</span>
                <el-input-number v-model="customCropH" size="small" :min="1" @change="setCustomCropAspect" controls-position="right" />
              </div>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">照片尺寸</div>
            <div class="ratio-row">
              <el-input-number v-model="targetWidth" :min="1" size="small" placeholder="宽(px)" />
              <el-input-number v-model="targetHeight" :min="1" size="small" placeholder="高(px)" />
              <el-checkbox v-model="lockRatio">锁定比例</el-checkbox>
              <el-button size="small" type="primary" @click="applySize">应用尺寸</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">旋转</div>
            <div class="rotate-row">
              <el-button size="small" @click="rotateStep(-90)">-90°</el-button>
              <el-button size="small" @click="rotateStep(90)">+90°</el-button>
              <span class="rotate-text">角度：{{ rotate }}°</span>
            </div>
            <div class="rotate-slider">
              <el-slider v-model="rotate" :min="ROTATE_MIN" :max="ROTATE_MAX" :step="1" @change="rotateSliderChange" />
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
