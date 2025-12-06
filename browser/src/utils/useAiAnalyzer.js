import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/http'

// 使用 AI 自动生成标题 / 描述 / 标签
export function useAiAnalyzer({ form, fileList, mergeTags }) {
  const analyzing = ref(false)

  const merge = mergeTags
    ? mergeTags
    : (incoming = []) => {
        const base = Array.isArray(form?.tags) ? form.tags : []
        const next = new Set(base)
        ;(Array.isArray(incoming) ? incoming : [incoming]).forEach((t) => {
          const name = (t || '').toString().trim()
          if (name) next.add(name)
        })
        form.tags = Array.from(next)
      }

  const analyze = async () => {
    if (!fileList?.value?.length) {
      ElMessage.warning('请先选择要分析的图片')
      return
    }
    const first = fileList.value[0]
    if (!first?.raw) {
      ElMessage.error('未找到图片源文件')
      return
    }

    analyzing.value = true
    try {
      const fd = new FormData()
      fd.append('file', first.raw)
      const { data } = await api.post('/api/v1/images/ai-analyze', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (data?.ok) {
        const aiTitle = data.title || ''
        if (!form.title && aiTitle) {
          form.title = aiTitle
        } else if (aiTitle) {
          console.info('[AI 推荐标题]', aiTitle)
        }
        form.description = data.description || ''
        merge(data.tags || [])
        ElMessage.success('AI 已分析完成，已填入标题、描述和标签')
      } else {
        ElMessage.error(data?.error || 'AI 分析失败')
      }
    } catch (e) {
      ElMessage.error(e?.response?.data?.error || 'AI 分析失败')
    } finally {
      analyzing.value = false
    }
  }

  return { analyzing, analyze }
}
