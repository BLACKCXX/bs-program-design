<script setup>
import { ref } from 'vue'
import { MagicStick, ChatLineRound, Loading } from '@element-plus/icons-vue'

const quickPrompts = [
  '找几张人物和城市夜景的照片',
  '有哪些动物主题的图片？',
  '列出最近上传的风景照',
  '帮我找有花和微距的作品',
]

const messages = ref([
  { role: 'ai', content: '嗨，我是 AI 图片助手，问我“帮我找夜景的照片”试试？' },
])

const input = ref('')
const sending = ref(false)

const send = (preset) => {
  const content = (preset ?? input.value).trim()
  if (!content) return
  messages.value.push({ role: 'user', content })
  input.value = ''
  sending.value = true
  setTimeout(() => {
    messages.value.push({
      role: 'ai',
      content: `AI 已收到：${content}，我会在真实接口接入后帮你筛选匹配的图片。`,
    })
    sending.value = false
  }, 600)
}
</script>

<template>
  <div class="ai-page">
    <div class="header">
      <div>
        <h2>AI 工作台 · 智能图片检索</h2>
        <p class="sub">与大模型对话，检索你的图片资产，或者让它帮你找灵感</p>
      </div>
      <el-tag type="success" effect="plain">实验室 · 本地模拟</el-tag>
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
        <el-tag type="warning" effect="plain">未来可连后端检索</el-tag>
      </div>
      <div class="messages">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="bubble-row"
          :class="msg.role"
        >
          <div class="bubble">
            <span v-if="msg.role === 'ai'" class="label">AI</span>
            <span v-else class="label user">Me</span>
            <p>{{ msg.content }}</p>
          </div>
        </div>
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

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-strong);
  font-weight: 700;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 220px;
  padding: 8px;
  background: #f0f5ff;
  border-radius: 12px;
  border: 1px dashed var(--border);
}

.bubble-row {
  display: flex;
}

.bubble-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 76%;
  background: #fff;
  border-radius: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
}

.bubble-row.user .bubble {
  background: linear-gradient(135deg, #e5f0ff, #d7e8ff);
}

.bubble p {
  margin: 6px 0 0;
  color: var(--text);
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
  border-color: var(--border);
  background: #fff;
}

@media (max-width: 720px) {
  .composer {
    flex-direction: column;
    align-items: stretch;
  }

  .bubble {
    max-width: 100%;
  }
}
</style>
