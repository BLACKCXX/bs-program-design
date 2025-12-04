<script setup>
//advise 前端详情页 + 图片编辑弹层（仅样式/本地状态，不改后端）
import { ref, computed, onMounted } from 'vue'
import api from '../api/http'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Share, Delete as DeleteIcon, ZoomOut, ZoomIn, FullScreen, MagicStick } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

//advise 统一拼接文件 URL，避免 /files 丢失域名
const API = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')
const toAbs = (p) => (p?.startsWith('http') ? p : (p ? API + p : ''))

//advise 默认空对象，接口返回后填充
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

const activeTab = ref('basic')
const zoom = ref(100)
const showGps = ref(false)
const newTag = ref('')
const tagTypes = ['success', 'warning', 'info', 'danger']

const visibilityOptions = [
const visibilityOptions = [
  { label: '??', value: 'public' },
  { label: '??', value: 'private' },
]
const fileInfo = computed(() => ({
const fileInfo = computed(() => ({
  sizeText: image.value.sizeMB ? `${image.value.sizeMB} MB` : '??',
  dimension: image.value.width && image.value.height ? `${image.value.width} ? ${image.value.height}` : '??',
}))
const onBack = () => router.back()
const changeZoom = (delta) => {
  zoom.value = Math.min(200, Math.max(50, zoom.value + delta))
}
const fitScreen = () => {
  zoom.value = 100
}
const onAction = (action) => {
  //advise 占位：后续可接入真实接口
  ElMessage.info(`${action} 功能待接入后端`)
}
const onFieldChange = () => {
  //advise 表单编辑占位
  console.log('TODO: save metadata to backend', image.value)
}
const removeTag = (tag) => {
  image.value.tags = image.value.tags.filter((t) => t !== tag)
  console.log('TODO: delete tag in backend', tag)
}
const addTag = () => {
  const name = (newTag.value || '').trim()
  if (!name) return
  if (!image.value.tags.includes(name)) {
    image.value.tags.push(name)
    console.log('TODO: add tag in backend', name)
  }
  newTag.value = ''
}
const toggleGps = () => {
  showGps.value = !showGps.value
}

//advise 记录图片尺寸与 DOM 尺寸
const onImgLoad = (e) => {
  const el = e.target
  imgNatural.value = { w: el.naturalWidth, h: el.naturalHeight }
  const rect = el.getBoundingClientRect()
  imgBox.value = { w: rect.width, h: rect.height }
  initCropRect()
}

//advise 裁剪拖拽开始
const startDrag = (evt, mode) => {
  if (!isCropping.value) return
  const rect = imgEl.value?.getBoundingClientRect()
  if (!rect) return
  dragState.value = {
    mode,
    startX: evt.clientX,
    startY: evt.clientY,
    box: rect,
    cropStart: { ...cropRect.value },
  }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', endDrag)
}

//advise 拖拽过程中换算到原始坐标
const onDrag = (evt) => {
  const st = dragState.value
  if (!st) return
  const dx = evt.clientX - st.startX
  const dy = evt.clientY - st.startY
  const fx = imgNatural.value.w / st.box.width
  const fy = imgNatural.value.h / st.box.height
  let { x, y, width, height } = st.cropStart
  const moveX = dx * fx
  const moveY = dy * fy

  const clamp = () => {
    x = Math.max(0, Math.min(imgNatural.value.w - width, x))
    y = Math.max(0, Math.min(imgNatural.value.h - height, y))
    width = Math.max(10, Math.min(imgNatural.value.w - x, width))
    height = Math.max(10, Math.min(imgNatural.value.h - y, height))
  }

  if (st.mode === 'move') {
    x += moveX
    y += moveY
    clamp()
  } else {
    if (st.mode.includes('e')) {
      width += moveX
    }
    if (st.mode.includes('w')) {
      x += moveX
      width -= moveX
    }
    if (st.mode.includes('s')) {
      height += moveY
    }
    if (st.mode.includes('n')) {
      y += moveY
      height -= moveY
    }
    clamp()
  }
  cropRect.value = { x, y, width, height }
}

//advise 拖拽结束
const endDrag = () => {
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', endDrag)
  dragState.value = null
}

//advise 拉取后端详情
const loadDetail = async () => {
  try {
    const { data } = await api.get(`/api/images/${route.params.id}`)
    const versionTag = Date.now() //advise 用时间戳做缓存破除，避免覆盖导出后仍显示旧图
    const absUrl = data.url ? `${toAbs(data.url)}?v=${versionTag}` : ''
    image.value = {
      ...emptyImage,
      ...data,
      url: absUrl, //advise 强制刷新图片内容，避免 304/缓存导致裁剪后无效
      exif: data.exif || {},
      relations: {
        parent: data.relations?.parent
          ? { ...data.relations.parent, thumb: data.relations.parent.thumb ? `${toAbs(data.relations.parent.thumb)}?v=${versionTag}` : '' }
          : null, //advise 关系缩略图也附带版本，避免看不到最新父图
        children: (data.relations?.children || []).map((c) => ({
          ...c,
          thumb: c.thumb ? `${toAbs(c.thumb)}?v=${versionTag}` : '',
        })), //advise 子图缩略图同样破缓存
      },
      tags: data.tags || [],
    }
    exportName.value = image.value.title || '' //advise 覆盖导出默认名称
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '加载图片详情失败')
  }
}
onMounted(loadDetail)

// ---------------- 编辑弹层状态 ----------------
const showEditor = ref(false) //advise 控制弹层
const isCompare = ref(false)
const history = ref([])

//advise 裁剪相关状态
const isCropping = ref(false)
const cropRatio = ref('free')
const customCropW = ref(1) //advise 自定义裁剪宽比
const customCropH = ref(1) //advise 自定义裁剪高比
const cropRect = ref({ x: 0, y: 0, width: 0, height: 0 }) //advise 以原始像素为单位
const pendingCrop = ref(null) //advise 存储待应用裁剪参数，导出时统一提交
const imgNatural = ref({ w: 0, h: 0 })
const imgBox = ref({ w: 0, h: 0 }) // DOM 尺寸
const imgEl = ref(null)
const dragState = ref(null) //advise 记录拖拽状态

const ROTATE_MIN = -180 //advise 旋转范围说明：-180 ~ 180
const ROTATE_MAX = 180
const rotate = ref(0)

const brightness = ref(0)
const contrast = ref(0)
const saturation = ref(0)
const warmth = ref(0)
const sharpen = ref(0)

const lockRatio = ref(true) //advise ????????
const targetWidth = ref(null) //advise ????
const targetHeight = ref(null) //advise ????


//advise 初始化裁剪框：居中 60%
const initCropRect = () => {
  if (!imgNatural.value.w || !imgNatural.value.h) return
  const w = imgNatural.value.w * 0.6
  const h = imgNatural.value.h * 0.6
  const x = (imgNatural.value.w - w) / 2
  const y = (imgNatural.value.h - h) / 2
  cropRect.value = { x, y, width: w, height: h }
}

const captureSnapshot = () => {
  //advise 每次修改前记录历史，便于撤销
  history.value.push({
    cropRatio: cropRatio.value,
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
  cropRatio.value = prev.cropRatio
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
}

const toggleCropMode = () => {
  isCropping.value = !isCropping.value
  if (isCropping.value) {
    if (pendingCrop.value) {
      cropRect.value = { ...pendingCrop.value }
    } else {
      initCropRect()
    }
  }
}

const cancelCrop = () => {
  isCropping.value = false
  if (pendingCrop.value) {
    cropRect.value = { ...pendingCrop.value }
  } else {
    initCropRect()
  }
}

const setCrop = (val) => {
  captureSnapshot()
  cropRatio.value = val
}
const setCustomCrop = () => {
  //advise 自定义比例：>0 生效并高亮
  if (customCropW.value > 0 && customCropH.value > 0) {
    captureSnapshot()
    cropRatio.value = `${customCropW.value}:${customCropH.value}`
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
}

//advise Size apply helper: optional custom width/height
const applySize = () => {
  if (lockRatio.value) {
    const parts = (cropRatio.value && cropRatio.value !== "free") ? cropRatio.value.split(":") : [image.value.width || 1, image.value.height || 1]
    const rw = Number(parts[0]) || 1
    const rh = Number(parts[1]) || 1
    if (targetWidth.value && !targetHeight.value) {
      targetHeight.value = Math.round((targetWidth.value / rw) * rh)
    } else if (!targetWidth.value && targetHeight.value) {
      targetWidth.value = Math.round((targetHeight.value / rh) * rw)
    }
  }
  ElMessage.info("Size applied; will be used on export")
}

//advise Crop button loading state to avoid double submit
const cropLoading = ref(false)
const applyCrop = () => {
  if (!isCropping.value) {
    ElMessage.warning("Enable crop mode and adjust the crop box first")
    return
  }
  if (cropLoading.value) return
  cropLoading.value = true
  try {
    captureSnapshot()
    pendingCrop.value = { ...cropRect.value }
    isCropping.value = false
    ElMessage.success('Crop applied locally; will submit on export')
  } finally {
    cropLoading.value = false
  }
}

const resetEditingState = () => {
  pendingCrop.value = null
  isCropping.value = false
  cropRatio.value = 'free'
  customCropW.value = 1
  customCropH.value = 1
  rotate.value = 0
  brightness.value = 0
  contrast.value = 0
  saturation.value = 0
  warmth.value = 0
  sharpen.value = 0
  targetWidth.value = null
  targetHeight.value = null
  lockRatio.value = true
  history.value = []
  isCompare.value = false
  exportName.value = image.value.title || ''
  initCropRect()
}

const closeEditor = () => {
  resetEditingState()
  showEditor.value = false
}

//advise Export: call backend /api/images/:id/edit, then refresh or jump to new image
//advise 导出：调用后端 /api/images/:id/edit，完成后刷新或跳转到新图详情
const exportMode = ref('override') // override | new
const exportName = ref('')
const onExport = async () => {
  if (exportMode.value === 'new' && !exportName.value.trim()) {
    ElMessage.warning('Please enter a name for the new image') //advise ????????
    return
  }
  const ratioParts = (cropRatio.value && cropRatio.value !== 'free') ? cropRatio.value.split(':') : []
  const payload = {
    mode: exportMode.value,
    exportName: exportName.value || image.value.title,
    rotate: rotate.value,
    crop_ratio: cropRatio.value, //advise 仅用于等比缩放参考，不做裁剪
    brightness: brightness.value,
    contrast: contrast.value,
    saturation: saturation.value,
    warmth: warmth.value,
    sharpen: sharpen.value,
    //advise 携带裁剪框（像素坐标）
    crop_rect: pendingCrop.value
      ? { ...pendingCrop.value }
      : (isCropping.value ? { ...cropRect.value } : null),
    //advise 尺寸调整
    target_width: targetWidth.value,
    target_height: targetHeight.value,
    keep_ratio: lockRatio.value,
    ratio_width: ratioParts.length === 2 ? Number(ratioParts[0]) || null : null,
    ratio_height: ratioParts.length === 2 ? Number(ratioParts[1]) || null : null,
  }
  try {
    console.log('[applyCrop/onExport] payload', payload) //advise 调试：确认已发送裁剪/尺寸参数
    const { data } = await api.post(`/api/images/${image.value.id}/edit`, payload)
    ElMessage.success('导出成功')
    if (data?.mode === 'new' && data?.image_id) {
      //advise 新建后跳转到新图片详情
      router.replace({ name: 'ImageDetail', params: { id: data.image_id } })
      closeEditor()
    } else {
      //advise 覆盖后刷新当前详情
      await loadDetail()
      closeEditor()
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '导出失败')
  }
}

//advise 预览样式：旋转 + 滤镜（裁剪通过容器裁切）
const appliedCrop = computed(() => (!isCropping.value ? pendingCrop.value : null))
const editedStyle = computed(() => {
  const filters = [
    `brightness(${1 + brightness.value / 100})`,
    `contrast(${1 + contrast.value / 100})`,
    `saturate(${1 + saturation.value / 100})`,
  ]
  const style = {
    filter: filters.join(' '),
  }
  const crop = appliedCrop.value
  const { w, h } = imgNatural.value
  if (crop && w && h && crop.width && crop.height) {
    const scaleX = w / crop.width
    const scaleY = h / crop.height
    style.width = `${scaleX * 100}%`
    style.height = `${scaleY * 100}%`
    style.transformOrigin = 'top left'
    const translateX = -(crop.x / crop.width) * 100
    const translateY = -(crop.y / crop.height) * 100
    style.transform = `translate(${translateX}%, ${translateY}%) rotate(${rotate.value}deg)`
  } else {
    style.transform = `rotate(${rotate.value}deg)`
  }
  return style
})

//advise DOM 裁剪框样式
const cropRectStyle = computed(() => {
  if (!isCropping.value) return {}
  const { w: dw, h: dh } = imgBox.value
  const { w: nw, h: nh } = imgNatural.value
  if (!dw || !dh || !nw || !nh) return {}
  const fx = dw / nw
  const fy = dh / nh
  const { x, y, width, height } = cropRect.value
  return {
    left: `${x * fx}px`,
    top: `${y * fy}px`,
    width: `${width * fx}px`,
    height: `${height * fy}px`,
  }
})
//advise Crop preview box style (aspect ratio + overflow to simulate crop)
const cropBoxStyle = computed(() => {
  if (isCropping.value) {
    const { w: dw, h: dh } = imgBox.value
    const { w: nw, h: nh } = imgNatural.value
    if (!dw || !dh || !nw || !nh) return {}
    return { position: 'relative', alignItems: 'start', justifyItems: 'start' }
  }
  const applied = appliedCrop.value
  if (applied && applied.width && applied.height) {
    return {
      aspectRatio: `${applied.width} / ${applied.height}`,
      overflow: 'hidden',
      position: 'relative',
      alignItems: 'start',
      justifyItems: 'start',
    }
  }
  if (!cropRatio.value || cropRatio.value === 'free') return {}
  const parts = cropRatio.value.split(':')
  if (parts.length !== 2) return {}
  const w = Number(parts[0]) || 1
  const h = Number(parts[1]) || 1
  return {
    aspectRatio: `${w} / ${h}`,
    overflow: 'hidden',
  }
})

<template>
  <div class="detail-page">
    <!-- 顶部导航 -->
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
        <!--advise 新按钮：图片编辑 -->
        <el-button text type="primary" :icon="MagicStick" @click="showEditor = true">图片编辑</el-button>
        <el-button text :icon="Download" @click="onAction('下载')">下载</el-button>
        <el-button text :icon="Share" @click="onAction('分享')">分享</el-button>
        <el-button text type="danger" :icon="DeleteIcon" @click="onAction('删除')">删除</el-button>
      </div>
    </header>

    <!-- 主体：左侧预览 + 右侧信息 -->
    <section class="detail-layout">
      <div class="preview-column">
        <div class="panel preview-panel">
          <div class="panel-header">
            <span class="panel-title">预览</span>
            <div class="zoom-bar">
              <el-button text :icon="ZoomOut" @click="changeZoom(-10)" />
              <span class="zoom-text">{{ zoom }}%</span>
              <el-button text :icon="ZoomIn" @click="changeZoom(10)" />
              <el-button text :icon="FullScreen" @click="fitScreen">适应屏幕</el-button>
            </div>
          </div>
          <div class="preview-body">
            <div class="img-wrap" :style="{ transform: `scale(${zoom / 100})` }">
              <img :src="image.url" :alt="image.title" />
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
              <el-button text type="primary" @click="addTag">+ 添加标签</el-button>
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
            <div class="add-tag-row">
              <el-input v-model="newTag" placeholder="输入新标签" @keyup.enter="addTag" />
              <el-button type="primary" @click="addTag">添加</el-button>
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
                <div class="block-title">父图片</div>
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
                <div class="block-title">子图片 {{ image.relations?.children?.length ? `(${image.relations.children.length})` : '' }}</div>
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

    <!-- 图片编辑弹层 -->
    <el-dialog v-model="showEditor" fullscreen :show-close="false" class="editor-dialog">
      <div class="editor-header">
        <div class="editor-title">图片编辑 - {{ image.title || '未命名' }}</div>
        <el-button type="primary" @click="closeEditor">关闭</el-button>
      </div>
      <div class="editor-body">
        <!-- 左侧预览区 -->
        <div class="editor-left">
          <div class="editor-toolbar">
            <div class="toolbar-actions">
              <el-button
                size="small"
                :type="isCropping ? 'primary' : 'default'"
                @click="toggleCropMode"
              >裁剪</el-button>
              <el-tag size="small" type="info">编辑中</el-tag>
              <el-button size="small" @click="isCompare = !isCompare" :disabled="isCropping">{{ isCompare ? '退出对比' : '双栏对比' }}</el-button>
              <el-button size="small" @click="undo">撤销</el-button>
            </div>
          </div>

          <div v-if="isCompare" class="compare-grid">
            <div class="card neutral">
              <div class="card-title">原图</div>
              <div class="card-img" :style="cropBoxStyle">
                <img :src="image.url" :alt="image.title" />
              </div>
            </div>
            <div class="card neutral">
              <div class="card-title">编辑后</div>
              <div class="card-img" :style="cropBoxStyle" ref="imgEl">
                <img :src="image.url" :alt="image.title" :style="editedStyle" @load="onImgLoad" />
                <div class="crop-overlay" v-if="isCropping">
                  <div class="crop-mask"></div>
                  <div class="crop-rect" :style="cropRectStyle" @mousedown.prevent="startDrag($event, 'move')">
                    <span class="handle handle-nw" @mousedown.stop.prevent="startDrag($event, 'nw')"></span>
                    <span class="handle handle-ne" @mousedown.stop.prevent="startDrag($event, 'ne')"></span>
                    <span class="handle handle-sw" @mousedown.stop.prevent="startDrag($event, 'sw')"></span>
                    <span class="handle handle-se" @mousedown.stop.prevent="startDrag($event, 'se')"></span>
                  </div>
                </div>
                <div class="crop-overlay" v-else-if="cropRatio !== 'free'">
                  <div class="crop-rect static"></div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="single-card neutral">
            <div class="card-title">编辑后</div>
            <div class="card-img" :style="cropBoxStyle" ref="imgEl">
              <img :src="image.url" :alt="image.title" :style="editedStyle" @load="onImgLoad" />
              <div class="crop-overlay" v-if="isCropping">
                <div class="crop-mask"></div>
                <div class="crop-rect" :style="cropRectStyle" @mousedown.prevent="startDrag($event, 'move')">
                  <span class="handle handle-nw" @mousedown.stop.prevent="startDrag($event, 'nw')"></span>
                  <span class="handle handle-ne" @mousedown.stop.prevent="startDrag($event, 'ne')"></span>
                  <span class="handle handle-sw" @mousedown.stop.prevent="startDrag($event, 'sw')"></span>
                  <span class="handle handle-se" @mousedown.stop.prevent="startDrag($event, 'se')"></span>
                </div>
              </div>
              <div class="crop-overlay" v-else-if="cropRatio !== 'free'">
                <div class="crop-rect static"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧控制面板 -->
        <div class="editor-right">
          <div class="panel neutral">
            <div class="panel-title">照片尺寸</div>
            <div class="ratio-row">
              <el-button-group>
                <el-button :type="cropRatio === 'free' ? 'primary' : 'default'" @click="setCrop('free')">自由</el-button>
                <el-button :type="cropRatio === '1:1' ? 'primary' : 'default'" @click="setCrop('1:1')">1:1</el-button>
                <el-button :type="cropRatio === '4:3' ? 'primary' : 'default'" @click="setCrop('4:3')">4:3</el-button>
                <el-button :type="cropRatio === '16:9' ? 'primary' : 'default'" @click="setCrop('16:9')">16:9</el-button>
              </el-button-group>
              <!--advise 自定义比例输入 -->
              <div class="custom-ratio">
                <span class="custom-label">自定义：</span>
                <el-input-number
                  v-model="customCropW"
                  size="small"
                  :min="1"
                  @change="setCustomCrop"
                  controls-position="right"
                />
                <span class="colon">:</span>
                <el-input-number
                  v-model="customCropH"
                  size="small"
                  :min="1"
                  @change="setCustomCrop"
                  controls-position="right"
                />
              </div>
            </div>
            <!--advise 尺寸输入 -->
            <div class="ratio-row">
              <el-input-number v-model="targetWidth" :min="1" size="small" placeholder="宽(px)" />
              <el-input-number v-model="targetHeight" :min="1" size="small" placeholder="高(px)" />
              <el-checkbox v-model="lockRatio">锁定比例</el-checkbox>
              <el-button size="small" type="primary" @click="applySize">应用尺寸</el-button>
            </div>
            <div class="ratio-row">
              <el-button
                size="small"
                type="primary"
                @click="applyCrop"
                :disabled="!isCropping"
                :loading="cropLoading"
              >应用裁剪</el-button>
              <el-button size="small" @click="cancelCrop">取消裁剪</el-button>
            </div>
          </div>

          <div class="panel neutral">
            <div class="panel-title">旋转</div>
            <div class="rotate-row">
              <el-button size="small" @click="rotateStep(-90)">← 90°</el-button>
              <el-button size="small" @click="rotateStep(90)">→ 90°</el-button>
              <span class="rotate-text">角度：{{ rotate }}°</span>
            </div>
            <!--advise 旋转滑条：-180~180 -->
            <div class="rotate-slider">
              <el-slider
                v-model="rotate"
                :min="ROTATE_MIN"
                :max="ROTATE_MAX"
                :step="1"
                @change="rotateSliderChange"
              />
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
              <el-slider v-model="warmth" :min="-100" :max="100" @change="captureSnapshot" />
            </div>
            <div class="slider-row">
              <span>锐化</span>
              <el-slider v-model="sharpen" :min="0" :max="100" @change="captureSnapshot" />
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
            <!--advise 导出名称输入 -->
            <div class="export-name">
              <span class="export-label">导出名称：</span>
              <el-input
                v-model="exportName"
                placeholder="请输入导出图片名称，如：可爱猫猫-v2"
                size="small"
              />
              <div class="export-tip">
                {{ exportMode === 'override' ? '覆盖时会以此名称更新原图标题' : '为新图片命名后再导出' }}
              </div>
            </div>
            <div class="export-actions">
              <el-button type="primary" @click="onExport">导出并保存</el-button>
              <el-button @click="closeEditor">取消</el-button>
            </div>
            <div class="export-note">
              <p>提示：未来可用“新建 + 删除原图”方式实现覆盖。</p>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 详情页样式（蓝/灰主题） */
.detail-page {
  background: #f5f7fa;
  min-height: 100vh;
  padding-bottom: 24px;
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
  display: flex;
  gap: 16px;
  padding: 16px;
}
.preview-column {
  flex: 3.4;
}
.side-column {
  flex: 1.2;
  max-width: 420px;
  min-width: 320px;
}
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
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
  min-height: 520px;
  display: flex;
  justify-content: center;
  align-items: center;
}
.img-wrap {
  transition: transform 0.2s ease;
  max-width: 100%;
  max-height: 70vh;
}
.img-wrap img {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  border-radius: 8px;
  object-fit: contain;
}
.side-tabs {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 10px;
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
.tag-list {
  display: flex;
  gap: 8px;
  flex-direction: column;
  margin-bottom: 12px;
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

/* 编辑弹层样式（蓝/灰主题） */
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
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--neutral-bg);
  height: calc(100vh - 60px);
  overflow: auto;
}
.editor-left {
  flex: 2;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.editor-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
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
.neutral {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}
.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.single-card {
  padding: 10px;
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
  background: #eef2f7;
  border-radius: 10px;
  padding: 8px;
  display: grid;
  place-items: center;
  min-height: 260px;
  width: 100%; /*advise 保持容器宽度用于裁剪 */
  height: 100%; /*advise 让图片填满裁剪容器 */
  overflow: hidden; /*advise 裁剪可视区域 */
}
.card-img img {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  object-fit: cover; /*advise 结合 overflow 隐藏模拟裁剪 */
}
.crop-overlay {
  position: absolute;
  inset: 8px;
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

@media (max-width: 1100px) {
  .detail-layout {
    flex-direction: column;
  }
  .preview-body {
    min-height: 320px;
  }
  .editor-body {
    flex-direction: column;
  }
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>