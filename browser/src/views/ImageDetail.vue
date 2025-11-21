<script setup>
// 新增详情页：直接使用后端数据渲染（不再用示例图）
import { ref, computed, onMounted } from 'vue'
import api from '../api/http' //advise 调用后端接口
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Crop, RefreshLeft, MagicStick, Download, Share, Delete as DeleteIcon, ZoomOut, ZoomIn, FullScreen } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

//advise 统一拼接后端域名，避免 /files 路径丢失 HOST
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

//advise 详情数据响应式存储
const image = ref({ ...emptyImage })

const activeTab = ref('basic') // 新增：Tabs 当前激活项
const zoom = ref(100) // 新增：预览缩放比例，百分比
const showGps = ref(false) // 新增：GPS 显示切换
const newTag = ref('') // 新增：新增标签输入框
const tagTypes = ['success', 'warning', 'info', 'danger'] // 新增：轮换标签颜色，保证不同标签视觉区分

const visibilityOptions = [
  { label: '公开', value: 'public' },
  { label: '私密', value: 'private' },
]

const fileInfo = computed(() => ({
  sizeText: image.value.sizeMB ? `${image.value.sizeMB} MB` : '未知',
  dimension: image.value.width && image.value.height ? `${image.value.width} × ${image.value.height}` : '未知',
}))

const onBack = () => router.back() // 新增：返回列表
const changeZoom = (delta) => {
  // 新增：简单缩放逻辑，限制在 50%~200%
  zoom.value = Math.min(200, Math.max(50, zoom.value + delta))
}
const fitScreen = () => {
  // 新增：适应屏幕重置
  zoom.value = 100
}
const onAction = (action) => {
  // 新增：操作按钮占位，后续可接入后端处理
  console.log(`TODO: 调用后端处理 ${action}`)
  ElMessage.info(`${action} 功能待接入后端`)
}
const onFieldChange = () => {
  // 新增：表单编辑占位，后续调用保存接口
  console.log('TODO: 调用后端保存元数据', image.value)
}
const removeTag = (tag) => {
  // 新增：本地移除标签
  image.value.tags = image.value.tags.filter((t) => t !== tag)
  console.log('TODO: 调用后端删除标签', tag)
}
const addTag = () => {
  // 新增：本地添加标签
  const name = (newTag.value || '').trim()
  if (!name) return
  if (!image.value.tags.includes(name)) {
    image.value.tags.push(name)
    console.log('TODO: 调用后端新增标签', name)
  }
  newTag.value = ''
}
const toggleGps = () => {
  // 新增：切换 GPS 显示
  showGps.value = !showGps.value
}

//advise 拉取后端详情数据，替换示例图
const loadDetail = async () => {
  try {
    const { data } = await api.get(`/api/images/${route.params.id}`)
    image.value = {
      ...emptyImage,
      ...data,
      url: toAbs(data.url),
      exif: data.exif || {},
      relations: {
        parent: data.relations?.parent ? { ...data.relations.parent, thumb: toAbs(data.relations.parent.thumb) } : null,
        children: (data.relations?.children || []).map((c) => ({ ...c, thumb: toAbs(c.thumb) })),
      },
      tags: data.tags || [],
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '加载图片详情失败')
  }
}

onMounted(loadDetail)
</script>

<template>
  <div class="detail-page">
    <!-- 顶部操作栏 -->
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
        <el-button text :icon="Crop" @click="onAction('裁剪')">裁剪</el-button>
        <el-button text :icon="RefreshLeft" @click="onAction('旋转')">旋转</el-button>
        <el-button text :icon="MagicStick" @click="onAction('滤镜')">滤镜</el-button>
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
            <!-- 新增：标签按行展示并轮换颜色，避免同一行挤在一起 -->
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
              <!-- 新增：EXIF 参数改为单列逐行展示，避免挤在同一行 -->
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
                  <img :src="image.relations?.parent?.thumb" alt="" />
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
  </div>
</template>

<style scoped>
/* 新增：详情页整体布局与样式 */
.detail-page {
  background: #f6f8fb;
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
  color: #374151;
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
  /* 新增：适度收窄右侧栏，避免过宽占比 */
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
  color: #374151;
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
  background: linear-gradient(135deg, #f3f4f6, #e5e7eb);
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
  color: #374151;
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
  /* 新增：标签单行展示 + 不同颜色 */
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
  background: #fef3c7;
  color: #92400e;
  padding: 8px 12px;
  border: 1px solid #fde68a;
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
  background: #f3f4f6;
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
  color: #2563eb;
}
.current-card {
  border: 1px solid #bfdbfe;
  background: #eff6ff;
}
.icon-box {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #e0f2fe;
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

@media (max-width: 1100px) {
  .detail-layout {
    flex-direction: column;
  }
  .preview-body {
    min-height: 320px;
  }
}
</style>
