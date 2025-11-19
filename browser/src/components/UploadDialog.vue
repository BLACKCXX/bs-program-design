<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '../api/http' // 预留：接入真实后端时可直接使用

// 父组件通过 v-model 控制开关；tagOptions 用于“与左侧筛选一致”的标签列表（动态）
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tagOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'uploaded'])

const visible = ref(false)
watch(() => props.modelValue, v => (visible.value = v), { immediate: true })
watch(visible, v => emit('update:modelValue', v))

// 表单与文件列表
const form = reactive({ title: '', description: '', tags: [] })
const fileList = ref([])

const accept = '.jpg,.jpeg,.png,.gif,.webp'
const MAX_SIZE = 10 * 1024 * 1024
const defaultTags = ['风景','人物','美食','建筑','动物','艺术','科技','运动','旅行','自然']
const allTags = computed(() => (props.tagOptions.length ? props.tagOptions : defaultTags))

// 选择文件校验（类型 + 大小）
function beforeUpload(file) {
  const okType = /image\/(jpeg|png|gif|webp)/i.test(file.type) || /\.(jpe?g|png|gif|webp)$/i.test(file.name)
  if (!okType) { ElMessage.error('仅支持 JPG/PNG/GIF/WEBP 格式'); return false }
  if (file.size > MAX_SIZE) { ElMessage.error('单个文件不能超过 10MB'); return false }
  return true
}
const onChange = (_file, files) => (fileList.value = files)
const onRemove = (_file, files) => (fileList.value = files)

function reset() {
  form.title = ''; form.description = ''; form.tags = []
  fileList.value = []
}

const uploading = ref(false)
// ⚠️ 现在用模拟上传；接入后端时把 USE_MOCK=false，并放开 api.post('/api/upload', ...)
const USE_MOCK = true

async function submit() {
  if (!fileList.value.length) return
  uploading.value = true
  try {
    const fd = new FormData()
    fileList.value.forEach(f => fd.append('files', f.raw))
    fd.append('title', form.title)
    fd.append('description', form.description)
    fd.append('tags', JSON.stringify(form.tags))

    if (USE_MOCK) {
      // 模拟后端耗时
      await new Promise(r => setTimeout(r, 800))
    } else {
      await api.post('/api/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    }

    ElMessage.success('上传成功')
    // 把关键信息回传给父组件（含预览用的临时URL，仅当前会话可见）
    emit('uploaded', {
      form: { ...form },
      files: fileList.value.map(f => ({
        name: f.name,
        size: f.size,
        url: URL.createObjectURL(f.raw),
      })),
    })
    visible.value = false
    reset()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '上传失败')
  } finally {
    uploading.value = false
  }
}

function onCancel() {
  visible.value = false
  reset()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="上传图片"
    width="680px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div class="uploader">
      <!-- 拖拽上传区 -->
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
          <div class="msg">拖拽图片到此处，或 <span class="link">点击上传</span></div>
          <div class="tips">支持 JPG、PNG、GIF、WEBP 格式，单个文件不超过 10MB</div>
        </div>
      </el-upload>

      <!-- 表单区 -->
      <el-form label-width="88px" class="mt">
        <el-form-item label="标题（可选）">
          <el-input v-model="form.title" placeholder="为这批图片添加标题" />
        </el-form-item>
        <el-form-item label="描述（可选）">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="添加描述信息..." />
        </el-form-item>
        <el-form-item label="标签（可选）">
          <el-select v-model="form.tags" multiple filterable collapse-tags placeholder="选择标签" style="width:100%;">
            <el-option v-for="t in allTags" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div class="footer">
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" :disabled="!fileList.length" :loading="uploading" @click="submit">开始上传</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.upload-box :deep(.el-upload) { width: 100%; }
.drag-area {
  border: 2px dashed #d1d5db; border-radius: 12px; background: #fafbff;
  text-align: center; padding: 26px 12px;
}
.icon { font-size: 44px; color: #90a4f6; margin-bottom: 6px; }
.msg { color: #374151; }
.msg .link { color: #2563eb; cursor: pointer; }
.tips { color: #9aa0a6; font-size: 12px; margin-top: 6px; }
.mt { margin-top: 14px; }
.footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
