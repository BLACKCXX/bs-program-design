<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '../api/http'
import { useAiAnalyzer } from '../utils/useAiAnalyzer'

const form = reactive({ title: '', description: '', tags: [] })
const fileList = ref([])

const accept = '.jpg,.jpeg,.png,.gif,.webp'
const MAX_SIZE = 10 * 1024 * 1024
const defaultTags = ['风景', '人物', '美食', '建筑', '动物', '艺术', '科技', '旅行', '自然']
const tagOptions = computed(() => defaultTags)

function beforeUpload(file) {
  const okType = /image\/(jpeg|png|gif|webp)/i.test(file.type) || /\.(jpe?g|png|gif|webp)$/i.test(file.name)
  if (!okType) { ElMessage.error('仅支持 JPG/PNG/GIF/WEBP 格式'); return false }
  if (file.size > MAX_SIZE) { ElMessage.error('单个文件不能超过 10MB'); return false }
  return true
}
const onChange = (_file, files) => (fileList.value = files)
const onRemove = (_file, files) => (fileList.value = files)

const uploading = ref(false)
const USE_MOCK = false

function reset() {
  form.title = ''
  form.description = ''
  form.tags = []
  fileList.value = []
}

// 合并标签并去重，保持已有选择
function mergeTags(newTags = []) {
  const incoming = Array.isArray(newTags) ? newTags : [newTags].filter(Boolean)
  const merged = new Set(form.tags || [])
  incoming.forEach((t) => {
    const name = (t || '').toString().trim()
    if (name) merged.add(name)
  })
  form.tags = Array.from(merged)
}

const { analyzing, analyze: analyzeByAI } = useAiAnalyzer({ form, fileList, mergeTags })

const submit = async () => {
  if (!fileList.value.length) {
    ElMessage.warning('请选择要上传的图片')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fileList.value.forEach((f) => fd.append('files', f.raw))
    fd.append('title', form.title)
    fd.append('description', form.description)
    fd.append('tags', JSON.stringify(form.tags))

    if (USE_MOCK) {
      await new Promise((r) => setTimeout(r, 800))
    } else {
      await api.post('/api/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    }
    ElMessage.success('上传成功')
    reset()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '上传失败')
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="upload-page">
    <div class="header">
      <div>
        <h2>上传中心 · 快来丰富你的专属图库吧！</h2>
        <p class="sub">支持多种图片格式，拖拽或点击选择，保持与你当前上传逻辑一致</p>
      </div>
      <el-tag type="success" effect="plain">使用现有上传接口</el-tag>
    </div>

    <div class="card grid">
      <div class="drop">
        <div class="drop-inner">
          <el-upload
            class="upload-box"
            drag
            multiple
            :auto-upload="false"
            :file-list="fileList"
            :before-upload="beforeUpload"
            :on-change="onChange"
            :on-remove="onRemove"
            :accept="accept"
          >
            <div class="drag-area">
              <el-icon class="icon"><UploadFilled /></el-icon>
              <div class="msg">拖拽或轻点选择</div>
              <div class="tips">支持 JPG / PNG / GIF / WEBP，单个文件不超过 10MB</div>
            </div>
          </el-upload>
          <div class="helper">
            手机可直接拍照或从相册选择，支持批量拖入
          </div>
        </div>
      </div>

      <div class="form">
        <div class="form-title">上传设置</div>
        <el-form label-position="top" class="form-body">
          <el-form-item label="自定义名称">
            <el-input v-model="form.title" placeholder="如：美丽的樱花（为空则用文件名）" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="可用于图片指引，支持多行"
            />
          </el-form-item>
          <el-form-item label="标签">
            <el-select
              v-model="form.tags"
              multiple
              filterable
              allow-create
              default-first-option
              collapse-tags
              :max-collapse-tags="4"
              :reserve-keyword="false"
              placeholder="输入或选择标签"
            >
              <el-option v-for="t in tagOptions" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="actions">
          <el-button @click="reset">清空选择</el-button>
          <el-button
            type="primary"
            plain
            :disabled="!fileList.length || uploading || analyzing"
            :loading="analyzing"
            @click="analyzeByAI"
          >
            AI 智能分析
          </el-button>
          <el-button type="primary" :loading="uploading" :disabled="!fileList.length || analyzing" @click="submit">
            开始上传
          </el-button>
        </div>
      </div>
    </div>

    <div class="card queue">
      <div class="queue-title">上传队列</div>
      <div v-if="!fileList.length" class="empty">暂时还没有待上传的图片～ 先从上面选择几张吧 💗</div>
      <div v-else class="queue-list">
        <div v-for="file in fileList" :key="file.uid" class="queue-item">
          <div class="name">{{ file.name }}</div>
          <div class="meta">{{ (file.size / 1024 / 1024).toFixed(1) }} MB</div>
        </div>
      </div>
    </div>
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

.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 12px 26px rgba(75, 140, 255, 0.08);
}

.grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 14px;
}

.drop {
  background: #fff;
  border-radius: 14px;
  border: 1px dashed var(--border);
  padding: 14px;
}

.drop-inner {
  background: linear-gradient(180deg, #f8fbff, #edf3ff);
  border-radius: 12px;
  border: 1px dashed var(--border);
  padding: 18px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
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

.form {
  background: #fff;
  border-radius: 14px;
  border: 1px dashed var(--border);
  padding: 12px;
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

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.queue {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.queue-title {
  font-weight: 700;
  color: var(--primary-strong);
}

.empty {
  color: var(--muted);
  font-size: 14px;
}

.queue-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.queue-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
}

.name {
  font-weight: 600;
  color: var(--text);
}

.meta {
  color: var(--muted);
  font-size: 13px;
  margin-top: 4px;
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
