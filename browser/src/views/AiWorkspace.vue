<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatLineRound, Loading, Delete } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import api from '../api/http'
import { useAiWorkspaceStore } from '../stores/aiWorkspace'
import { toDisplayUrl } from '../utils/url'

const router = useRouter()
const workspaceStore = useAiWorkspaceStore()
workspaceStore.hydrate()

const { messages, tagSuggestions, lastQuery } = storeToRefs(workspaceStore)
const toAbs = (p) => toDisplayUrl(p)

const quickPrompts = [
  '帮我找几张晚霞的照片',
  '有哪些城市夜景和人物的图片？',
  '列出最近上传的风景照',
  '找找看有花朵和微距的作品',
]

const input = ref('')
const sending = ref(false)
const typingMsg = ref(null)
const messagesEl = ref(null)
const allTags = ref([])
const loadingTags = ref(false)
const requestId = ref(0)

const appendMessage = (payload, { persist = true } = {}) => {
  const msg = workspaceStore.pushMessage(payload)
  if (persist) workspaceStore.persist()
  return msg
}

const synonymMap = {
  风景: ['景色', '自然', '山水'],
  夜景: ['夜晚', '夜色'],
  人物: ['人像', '肖像'],
  建筑: ['楼宇', '街景', '城市建筑'],
  旅行: ['旅途', '旅游'],
  自然: ['户外', '森林'],
  美食: ['美味', '料理'],
}

const loadAllTags = async () => {
  if (loadingTags.value || allTags.value.length) return
  loadingTags.value = true
  try {
    const { data } = await api.get('/api/tags')
    allTags.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.warn('[aiWorkspace] load tags failed', err)
  } finally {
    loadingTags.value = false
  }
}

const tokenize = (text = '') => {
  const base = (text || '').trim()
  if (!base) return []
  const parts = base.split(/[\s,，。；;、/]+/).filter(Boolean)
  if (base.length >= 2) {
    for (let i = 0; i < base.length - 1; i += 1) {
      const seg = base.slice(i, i + 2).trim()
      if (seg && !parts.includes(seg)) parts.push(seg)
    }
  }
  return parts.slice(0, 12)
}

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

const latestResultsFromHistory = () => {
  const reversed = [...messages.value].reverse()
  const found = reversed.find((msg) => msg.type === 'results' && Array.isArray(msg.results) && msg.results.length)
  return found?.results || []
}

const refreshTagSuggestions = (query = '', results = []) => {
  const tokens = tokenize(query)
  const freq = {}
  results.forEach((res) => {
    ;(res?.tags || []).forEach((t) => {
      const name = (t || '').trim()
      if (name) freq[name] = (freq[name] || 0) + 1
    })
  })
  const candidates = new Set([...allTags.value, ...Object.keys(freq)])
  const scored = []
  candidates.forEach((tag) => {
    const name = (tag || '').toString().trim()
    if (!name) return
    const lower = name.toLowerCase()
    let score = (freq[name] || 0) * 1.2
    tokens.forEach((tok) => {
      const lt = tok.toLowerCase()
      if (!lt) return
      if (lower === lt) score += 4
      else if (lower.includes(lt)) score += 2.6
      else if (lt.includes(lower)) score += 2
      else {
        const overlap = [...new Set(lt.split(''))].filter((ch) => lower.includes(ch)).length
        score += overlap * 0.3
      }
    })
    Object.entries(synonymMap).forEach(([base, syns]) => {
      if (base === name || syns.includes(name)) {
        const hit = tokens.some((t) => base.includes(t) || syns.some((s) => s.includes(t)))
        if (hit) score += 2.2
      }
    })
    scored.push({ tag: name, score })
  })
  scored.sort((a, b) => b.score - a.score || a.tag.localeCompare(b.tag, 'zh-Hans-CN'))
  workspaceStore.setTagSuggestions(scored.slice(0, 12).map((it) => it.tag))
  workspaceStore.persist()
}

const scrollToBottom = async () => {
  await nextTick()
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

const discardTyping = () => {
  if (!typingMsg.value) return
  const idx = messages.value.indexOf(typingMsg.value)
  if (idx >= 0) messages.value.splice(idx, 1)
  typingMsg.value = null
}

const finalizeTyping = (payload = {}) => {
  if (!typingMsg.value) return
  Object.assign(typingMsg.value, payload)
  typingMsg.value = null
  workspaceStore.persist()
}

const removeMessage = (msg) => {
  if (!msg?.id) return
  workspaceStore.removeMessage(msg.id)
  if (!messages.value.length) {
    workspaceStore.setLastQuery('')
    workspaceStore.setTagSuggestions([])
  } else if (lastQuery.value) {
    refreshTagSuggestions(lastQuery.value, latestResultsFromHistory())
  }
  workspaceStore.persist()
}

const clearMessages = async () => {
  if (!messages.value.length) return
  try {
    await ElMessageBox.confirm('确认清空所有对话记录吗？', '清空记录', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (err) {
    return
  }
  discardTyping()
  workspaceStore.clearAll()
  input.value = ''
}

const normalizeResult = (item = {}) => {
  const tags = Array.isArray(item.tags) ? [...item.tags] : []
  const suggested = Array.isArray(item.suggestedTags) ? [...item.suggestedTags] : []
  const cover = toAbs(item.coverUrl || item.thumbUrl || '')
  const thumb = toAbs(item.thumbUrl || item.coverUrl || '')
  const detailUrl = item.detailUrl || item.detail_url || (item.id ? `/images/${item.id}` : '')
  const matchedFields = Array.isArray(item.matchedFields)
    ? item.matchedFields
    : Array.isArray(item.matched_fields)
      ? item.matched_fields
      : []
  return {
    id: item.id,
    title: item.title || '未命名',
    description: item.description || '',
    shortCaption: item.shortCaption || item.description || '',
    coverUrl: cover || thumb,
    thumbUrl: thumb || cover,
    tags,
    suggestedTags: suggested,
    matchedFields,
    detailUrl,
    score: item.score != null ? item.score : null,
  }
}

// 发送检索请求，使用 AI 兜底补充推荐标签
const send = async (preset) => {
  const content = (preset ?? input.value).trim()
  if (!content || sending.value) return
  const currentReq = ++requestId.value

  appendMessage({ role: 'user', type: 'text', content })
  workspaceStore.setLastQuery(content)
  workspaceStore.persist()
  await scrollToBottom()

  input.value = ''
  sending.value = true
  typingMsg.value = appendMessage({ role: 'ai', type: 'typing', content: '' }, { persist: false })
  await scrollToBottom()
  refreshTagSuggestions(content, latestResultsFromHistory())

  try {
    const { data } = await api.post('/api/ai/chat-search', { message: content })
    if (currentReq !== requestId.value) {
      discardTyping()
      return
    }
    const isError = data && data.ok === false
    if (isError) {
      const msg = data.error || data.detail || '请求失败'
      ElMessage.error(msg)
      finalizeTyping({ type: 'text', content: msg, results: [] })
      await scrollToBottom()
      return
    }

    const rawResults = Array.isArray(data?.results) ? data.results : []
    const results = rawResults.map(normalizeResult)
    const replyText = data?.reply || '我先为你整理了相关图片。'
    finalizeTyping({ type: results.length ? 'results' : 'text', content: replyText, results })
    refreshTagSuggestions(content, results)
  } catch (err) {
    if (currentReq !== requestId.value) {
      discardTyping()
      return
    }
    const msg = err?.response?.data?.error || err?.response?.data?.detail || '请求失败'
    ElMessage.error(msg)
    finalizeTyping({ type: 'text', content: msg, results: [] })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}



const applyTagSuggestion = (tag) => {
  const name = (tag || '').trim()
  if (!name) return
  input.value = name
  if (!sending.value) {
    send(name)
  }
}

const openDetail = (payload) => {
  if (!payload) return
  const detailUrl = typeof payload === 'object' ? payload.detailUrl : null
  const id = typeof payload === 'object' ? payload.id : payload
  if (detailUrl) {
    router.push(detailUrl)
    return
  }
  if (id) {
    router.push({ name: 'ImageDetail', params: { id } })
  }
}

const removeSuggested = (res, tag) => {
  if (!Array.isArray(res.suggestedTags)) return
  const idx = res.suggestedTags.indexOf(tag)
  if (idx >= 0) res.suggestedTags.splice(idx, 1)
}

// 采纳 AI 推荐标签：写入后端并更新当前卡片的标签列表
const acceptTag = async (res, tag) => {
  if (!res?.id) return
  try {
    const { data } = await api.post(`/api/images/${res.id}/tags/accept_suggestions`, { tags: [tag] })
    const returned = Array.isArray(data?.tags) ? data.tags : []
    res.tags = returned.length ? returned : Array.from(new Set([...(res.tags || []), tag]))
    ElMessage.success('已采纳标签')
  } catch (err) {
    ElMessage.error(err?.response?.data?.error || '采纳标签失败')
    return
  }
  removeSuggested(res, tag)
}

const rejectTag = (res, tag) => {
  removeSuggested(res, tag)
}

onMounted(async () => {
  await nextTick()
  await scrollToBottom()
  await loadAllTags()
  if (lastQuery.value) {
    refreshTagSuggestions(lastQuery.value, latestResultsFromHistory())
  } else {
    refreshTagSuggestions('', latestResultsFromHistory())
  }
})

watch(
  () => input.value,
  (val) => {
    if (!sending.value) refreshTagSuggestions(val, latestResultsFromHistory())
  }
)
</script>

<template>
  <div class="ai-page">
    <div class="header">
      <div>
        <h2>AI 工作台 · 智能图片检索</h2>
        <p class="sub">与大模型对话，检索你的图片资产，或让它额外做内容分析补全结果</p>
      </div>
      <el-tag type="success" effect="plain">支持兜底内容分析</el-tag>
    </div>

    <div class="card prompt-card">
      <div class="prompt-title">
        <el-icon><MagicStick /></el-icon>
        <span>快捷提示</span>
      </div>
      <div class="prompt-buttons">
        <el-button
          v-for="prompt in quickPrompts"
          :key="prompt"
          round
          plain
          type="primary"
          @click="send(prompt)"
        >
          {{ prompt }}
        </el-button>
      </div>
    </div>

    <div class="card chat-card">
      <div class="chat-head">
        <div class="title">
          <el-icon><ChatLineRound /></el-icon>
          <span>对话区</span>
        </div>
        <div class="chat-actions">
          <el-button text type="danger" :disabled="!messages.length" @click="clearMessages">????</el-button>
          <el-tag type="warning" effect="plain">已接入 AI 检索与推荐标签</el-tag>
        </div>
      </div>
      <div v-if="tagSuggestions?.length" class="tag-suggest">
        <div class="tag-suggest-title">AI 推荐标签（基于图库已有标签）</div>
        <div class="tag-suggest-list">
          <el-check-tag
            v-for="tag in tagSuggestions"
            :key="tag"
            class="tag-suggest-chip"
            @click="applyTagSuggestion(tag)"
          >
            {{ tag }}
          </el-check-tag>
        </div>
      </div>
      <div class="messages" ref="messagesEl">
        <transition-group name="msg-fade" tag="div">
          <div
            v-for="(msg, idx) in messages"
            :key="msg.id || idx"
            class="bubble-row"
            :class="msg.role"
          >
            <div class="avatar" :class="msg.role">{{ msg.role === 'ai' ? 'AI' : 'Me' }}</div>
            <div class="bubble">
              <div class="bubble-header">
                <div class="bubble-meta">
                  <span v-if="msg.role === 'ai'" class="label">AI</span>
                  <span v-else class="label user">Me</span>
                  <span v-if="msg.timestamp" class="time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <el-button
                  v-if="msg.type !== 'typing'"
                  class="delete-btn"
                  text
                  :icon="Delete"
                  @click.stop="removeMessage(msg)"
                />
              </div>
              <p v-if="msg.type === 'text' && msg.content">{{ msg.content }}</p>
              <div v-else-if="msg.type === 'typing'" class="typing-dots">
                <span></span><span></span><span></span>
              </div>
              <div v-else-if="msg.type === 'results'" class="result-block">
                <p v-if="msg.content" class="result-text">{{ msg.content }}</p>
                <div v-if="msg.results?.length" class="result-grid">
                  <div
                    v-for="item in msg.results"
                    :key="item.id || item.detailUrl"
                    class="result-thumb"
                    @click="openDetail(item)"
                  >
                    <el-image
                      v-if="item.thumbUrl"
                      :src="item.thumbUrl"
                      fit="cover"
                      class="thumb-img"
                    />
                    <span v-else class="thumb-placeholder">No Image</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition-group>
      </div>
      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          placeholder="描述你想找的图片场景、风格或对象..."
          resize="none"
        />
        <el-button
          type="primary"
          size="large"
          :icon="sending ? Loading : MagicStick"
          :loading="sending"
          @click="send()"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-page {
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

.prompt-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-strong);
  font-weight: 700;
  margin-bottom: 10px;
}

.prompt-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.chat-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-strong);
  font-weight: 700;
}

.tag-suggest {
  background: #f9fbff;
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 10px 12px;
}

.tag-suggest-title {
  color: var(--primary-strong);
  font-weight: 700;
  margin-bottom: 6px;
}

.tag-suggest-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-suggest-chip {
  border-radius: 999px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  background: #fff;
  cursor: pointer;
}

.tag-suggest-chip:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 260px;
  padding: 8px;
  background: #f0f5ff;
  border-radius: 12px;
  border: 1px dashed var(--border);
  overflow-y: auto;
}

.msg-fade-enter-active,
.msg-fade-leave-active {
  transition: all 0.2s ease;
}
.msg-fade-enter-from,
.msg-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.bubble-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.bubble-row.user {
  justify-content: flex-start;
  flex-direction: row;
}

.bubble-row.ai {
  justify-content: flex-end;
  flex-direction: row-reverse;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: #dbeafe;
  color: var(--primary-strong);
  border: 1px solid var(--border);
}

.avatar.ai {
  background: #eef2ff;
  color: var(--primary-strong);
}

.bubble {
  max-width: 86%;
  background: #fff;
  border-radius: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
  position: relative;
}

.bubble-row.user .bubble {
  background: linear-gradient(135deg, #e5f0ff, #d7e8ff);
}

.bubble-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.bubble-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time {
  font-size: 12px;
  color: var(--muted);
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s ease;
}

.bubble:hover .delete-btn {
  opacity: 1;
}

.bubble p {
  margin: 6px 0 8px;
  color: var(--text);
}

.typing-dots {
  display: inline-flex;
  gap: 4px;
  padding: 6px 0;
}
.typing-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  opacity: 0.6;
  animation: blink 1s infinite ease-in-out;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 100% { opacity: 0.2; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-2px); }
}

.label {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary);
  background: var(--soft);
  padding: 2px 8px;
  border-radius: 999px;
}

.label.user {
  color: var(--primary-strong);
  background: #dbeafe;
}

.composer {
  display: flex;
  gap: 10px;
  align-items: center;
}

.composer :deep(.el-textarea__inner) {
  border-radius: 12px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.result-block {
  margin-top: 4px;
}

.result-text {
  margin: 4px 0 8px;
  color: var(--text);
  line-height: 1.6;
}

.result-thumb {
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: #f8fbff;
  cursor: pointer;
  transition: all 0.15s ease;
  aspect-ratio: 4 / 3;
  display: grid;
  place-items: center;
}

.result-thumb:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(75, 140, 255, 0.18);
}

.thumb-img {
  width: 100%;
  height: 100%;
}

.thumb-img :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  color: var(--muted);
  font-size: 13px;
}

.result-empty {
  margin-top: 8px;
  padding: 10px;
  background: #fff7ed;
  border: 1px dashed #fdba74;
  border-radius: 8px;
  color: #c2410c;
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: space-between;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .ai-page {
    gap: 12px;
  }

  .header {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .card {
    padding: 12px;
  }

  .prompt-buttons {
    flex-wrap: wrap;
    gap: 8px;
  }

  .prompt-buttons :deep(.el-button) {
    width: 100%;
    justify-content: flex-start;
    min-height: 44px;
  }

  .chat-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .messages {
    max-height: 55vh;
    min-height: 220px;
  }

  .bubble {
    max-width: 100%;
  }

  .result-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  }

  .composer {
    flex-direction: column;
    align-items: stretch;
  }

  .composer :deep(.el-button) {
    width: 100%;
    min-height: 46px;
  }
}
</style>
