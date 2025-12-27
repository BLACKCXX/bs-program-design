import { defineStore } from 'pinia'

const STORAGE_KEY = 'ai_workspace_state_v1'
const VERSION = 1

const defaultMessages = [
  { role: 'ai', type: 'text', content: '嗨，我是 AI 图片助手，问我“帮我找晚霞的照片”试试？' },
]

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
        if (Array.isArray(parsed.messages)) this.messages = parsed.messages
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
      this.messages = [...defaultMessages]
      this.tagSuggestions = []
      this.lastQuery = ''
      this.persist()
    },
    setMessages(list) {
      this.messages = Array.isArray(list) ? list : []
    },
    pushMessage(msg) {
      if (msg) this.messages.push(msg)
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
