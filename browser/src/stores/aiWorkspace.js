import { defineStore } from 'pinia'

const STORAGE_KEY = 'ai_workspace_state_v1'
const VERSION = 1
const MAX_MESSAGES = 200

const buildMessageId = () => `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
const normalizeRole = (role) => {
  const raw = (role || '').toString().toLowerCase()
  if (['ai', 'assistant', 'bot'].includes(raw)) return 'ai'
  if (['user', 'me', 'human'].includes(raw)) return 'user'
  return raw === 'system' ? 'ai' : 'ai'
}
const normalizeMessage = (msg) => {
  if (!msg || typeof msg !== 'object') return null
  return {
    ...msg,
    id: msg.id || buildMessageId(),
    timestamp: typeof msg.timestamp === 'number' ? msg.timestamp : Date.now(),
    role: normalizeRole(msg.role),
    type: msg.type || 'text',
    content: msg.content || '',
  }
}
const normalizeMessages = (list) => (Array.isArray(list) ? list.map(normalizeMessage).filter(Boolean) : [])
const buildDefaultMessages = () => [
  normalizeMessage({ role: 'ai', type: 'text', content: '嗨，我是 AI 图片助手，问我“帮我找晚霞的照片”试试？' }),
]
const defaultMessages = buildDefaultMessages()

export const useAiWorkspaceStore = defineStore('aiWorkspace', {
  state: () => ({
    messages: [...defaultMessages],
    tagSuggestions: [],
    lastQuery: '',
  }),
  actions: {
    hydrate() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (!raw) return
        const parsed = JSON.parse(raw)
        if (!parsed || parsed.version !== VERSION) return
        if (Array.isArray(parsed.messages)) {
          const normalized = normalizeMessages(parsed.messages)
          this.messages = normalized.length ? normalized : buildDefaultMessages()
        }
        if (Array.isArray(parsed.tagSuggestions)) this.tagSuggestions = parsed.tagSuggestions
        if (typeof parsed.lastQuery === 'string') this.lastQuery = parsed.lastQuery
      } catch (err) {
        console.warn('[aiWorkspace] hydrate failed', err)
      }
    },
    persist() {
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            version: VERSION,
            messages: this.messages,
            tagSuggestions: this.tagSuggestions,
            lastQuery: this.lastQuery,
          })
        )
      } catch (err) {
        console.warn('[aiWorkspace] persist failed', err)
      }
    },
    reset() {
      this.messages = buildDefaultMessages()
      this.tagSuggestions = []
      this.lastQuery = ''
      this.persist()
    },
    setMessages(list) {
      const normalized = normalizeMessages(list)
      this.messages = normalized.length > MAX_MESSAGES ? normalized.slice(-MAX_MESSAGES) : normalized
    },
    pushMessage(msg) {
      const normalized = normalizeMessage(msg)
      if (!normalized) return null
      this.messages.push(normalized)
      if (this.messages.length > MAX_MESSAGES) {
        this.messages.splice(0, this.messages.length - MAX_MESSAGES)
      }
      return normalized
    },
    removeMessage(id) {
      if (!id) return
      this.messages = this.messages.filter((msg) => msg.id !== id)
    },
    clearAll() {
      this.messages = []
      this.tagSuggestions = []
      this.lastQuery = ''
      this.persist()
    },
    setTagSuggestions(list) {
      this.tagSuggestions = Array.isArray(list) ? list : []
    },
    setLastQuery(q) {
      this.lastQuery = q || ''
    },
  },
})

export const defaultAiMessages = defaultMessages
