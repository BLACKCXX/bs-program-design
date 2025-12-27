
<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, Monitor, Iphone } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import heroImg from '../assets/login/hero.png'
import previewImg from '../assets/login/login.png'

const router = useRouter()
const route = useRoute()
const store = useAuthStore()

const panel = ref('welcome') // 'welcome' | 'login' | 'register'

// 表单 & 校验
const loginForm = reactive({ identifier: '', password: '' })
const loginRules = {
  identifier: [{ required: true, message: '请输入邮箱或用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const regForm = reactive({ email: '', username: '', password: '', confirm: '' })
const regRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码（≥6位）', trigger: 'blur' },
    { min: 6, message: '至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: (_, v, cb) => (v === regForm.password ? cb() : cb(new Error('两次输入不一致'))), trigger: 'blur' },
  ],
}

const loginLoading = ref(false)
const regLoading = ref(false)

const loginRef = ref()
const regRef = ref()

const formatError = (e, fallback) => {
  if (e?.response) {
    const status = e.response.status
    const msg = e.response.data?.error || e.response.data?.message || e.response.statusText || fallback
    return `${msg}${status ? `（${status}）` : ''}`
  }
  return '无法连接后端，请检查后端是否启动、端口/代理设置'
}

const switchPanel = (mode) => {
  panel.value = mode
}

const doLogin = async () => {
  await loginRef.value?.validate(async (ok) => {
    if (!ok) return
    loginLoading.value = true
    try {
      await store.login(loginForm.identifier.trim(), loginForm.password)
      ElMessage.success('登录成功')
      const redirect = route.query.redirect || '/'
      router.replace(String(redirect))
    } catch (e) {
      ElMessage.error(formatError(e, '登录失败'))
    } finally {
      loginLoading.value = false
    }
  })
}

const doRegister = async () => {
  await regRef.value?.validate(async (ok) => {
    if (!ok) return
    regLoading.value = true
    try {
      await store.register(regForm.email.trim(), regForm.username.trim(), regForm.password)
      ElMessage.success('注册成功，请登录')
      panel.value = 'login'
    } catch (e) {
      ElMessage.error(formatError(e, '注册失败'))
    } finally {
      regLoading.value = false
    }
  })
}
</script>

<template>
  <div class="auth-page">
    <div class="top-right-ctrl surface">
      <button :class="['seg-btn', panel === 'login' && 'on']" @click="switchPanel('login')">Login</button>
      <button :class="['seg-btn', panel === 'register' && 'on']" @click="switchPanel('register')">Register</button>
    </div>

    <div class="auth-shell">
      <div class="hero-pane surface">
        <div class="hero-bg">
          <!-- hero.png 仅渲染一次作为底图 -->
          <div class="hero-bg-img"></div>
          <!-- login.png 仅渲染一次作为预览叠图 -->
          <img class="hero-preview" :src="previewImg" alt="preview" />
          <div class="hero-overlay"></div>
        </div>
        <div class="hero-content">
          <div class="hero-text">
            <p class="eyebrow">Private Picture Shop</p>
            <h1 class="hero-title">请你来探索</h1>
            <p class="hero-sub"></p>
          </div>
          <div class="hero-badges">
            <span class="pill surface">
              <el-icon><MagicStick /></el-icon>
              AI 检索
            </span>
            <span class="pill surface">
              <el-icon><Monitor /></el-icon>
              PC 端
            </span>
            <span class="pill surface">
              <el-icon><Iphone /></el-icon>
              iOS / Android
            </span>
          </div>
        </div>
      </div>

      <div class="content-pane">
        <transition name="slide-fade-right" mode="out-in">
          <div v-if="panel === 'welcome'" key="welcome" class="welcome-text surface-nocard">
            <h2>欢迎探索，打造自己的空间</h2>
            <p>点击右上角 Login / Register 开始使用</p>
          </div>

          <div v-else-if="panel === 'login'" key="login" class="form-wrap surface">
            <div class="form-head">
              <div>
                <p class="form-sub">Welcome</p>
                <h3 class="form-title">登录你的创作空间</h3>
              </div>
              <button class="back-btn" @click="switchPanel('welcome')">返回</button>
            </div>
            <el-form ref="loginRef" :model="loginForm" :rules="loginRules" label-position="top">
              <el-form-item label="邮箱 / 用户名" prop="identifier">
                <el-input v-model="loginForm.identifier" placeholder="请输入邮箱或用户名" autocomplete="username" />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="请输入密码"
                  show-password
                  autocomplete="current-password"
                />
              </el-form-item>
              <div class="actions">
                <a class="link" href="javascript:;">忘记密码？</a>
              </div>
              <el-button type="primary" class="submit" :loading="loginLoading" @click="doLogin">登录</el-button>
            </el-form>
          </div>

          <div v-else key="register" class="form-wrap surface">
            <div class="form-head">
              <div>
                <p class="form-sub">Hello</p>
                <h3 class="form-title">注册新账号</h3>
              </div>
              <button class="back-btn" @click="switchPanel('welcome')">返回</button>
            </div>
            <el-form ref="regRef" :model="regForm" :rules="regRules" label-position="top">
              <el-form-item label="邮箱" prop="email">
                <el-input v-model="regForm.email" placeholder="请输入邮箱" autocomplete="email" />
              </el-form-item>
              <el-form-item label="用户名" prop="username">
                <el-input v-model="regForm.username" placeholder="请输入用户名" autocomplete="username" />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="regForm.password"
                  type="password"
                  placeholder="请输入密码（至少6位）"
                  show-password
                  autocomplete="new-password"
                />
              </el-form-item>
              <el-form-item label="确认密码" prop="confirm">
                <el-input
                  v-model="regForm.confirm"
                  type="password"
                  placeholder="请再次输入密码"
                  show-password
                  autocomplete="new-password"
                />
              </el-form-item>
              <el-button type="primary" class="submit" :loading="regLoading" @click="doRegister">注册</el-button>
            </el-form>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5fbff, #e9f2ff);
  padding: 32px 18px 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0f172a;
}

.top-right-ctrl {
  position: fixed;
  top: 24px;
  right: 24px;
  display: inline-flex;
  background: #ffffffec;
  border: 1px solid #d7e8ff;
  border-radius: 999px;
  padding: 6px;
  gap: 6px;
  z-index: 20;
}

.seg-btn {
  border: 1px solid #d7e8ff;
  background: #f7fbff;
  color: #1f2b44;
  padding: 9px 18px;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 700;
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.seg-btn.on {
  background: linear-gradient(135deg, #8ad1ff, #5ea8ff);
  color: #0f172a;
  border-color: transparent;
  box-shadow: 0 10px 20px rgba(94, 168, 255, 0.25);
}

.seg-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(90, 150, 255, 0.2), 0 0 24px rgba(94, 168, 255, 0.2);
}

.seg-btn:active {
  transform: translateY(1px);
  box-shadow: 0 6px 12px rgba(90, 150, 255, 0.15);
}

.auth-shell {
  width: min(1280px, 100%);
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 28px;
  align-items: center;
}

.hero-pane {
  border-radius: 28px;
  overflow: hidden;
  position: relative;
  background: #f7fbff;
  min-height: 540px;
}

.hero-bg {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.hero-bg-img {
  position: absolute;
  inset: 0;
  background-image: url('../assets/login/hero.png');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  filter: blur(8px);
  opacity: 0.9;
}

.hero-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.24), rgba(240, 248, 255, 0.65));
  z-index: 2;
}

.hero-preview {
  position: absolute;
  right: 18px;
  bottom: 18px;
  width: clamp(360px, 82%, 560px);
  border-radius: 18px;
  transform: rotate(-2deg);
  opacity: 0.95;
  z-index: 3;
  box-shadow: 0 18px 36px rgba(43, 93, 168, 0.35);
  pointer-events: none;
}

.hero-content {
  position: relative;
  z-index: 4;
  padding: 32px;
  min-height: 540px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 16px;
}

.eyebrow {
  margin: 0;
  letter-spacing: 1px;
  color: #1f4fb8;
  font-weight: 800;
  font-size: 15px;
}

.hero-title {
  margin: 0;
  font-size: clamp(42px, 4.2vw, 56px);
  line-height: 1.08;
  font-weight: 900;
  color: #0c1b3a;
}

.hero-sub {
  margin: 0;
  color: #1f2b44;
  font-size: 18px;
  line-height: 1.6;
}

.hero-badges {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d6e7ff;
  color: #1d4ed8;
  font-weight: 700;
  box-shadow: 0 8px 18px rgba(89, 145, 255, 0.18);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.pill:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(89, 145, 255, 0.24), 0 0 22px rgba(94, 168, 255, 0.22);
}

.pill:active {
  transform: translateY(1px);
  box-shadow: 0 8px 16px rgba(89, 145, 255, 0.16);
}

.content-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
  justify-content: center;
}

.welcome-text {
  padding: 10px 4px;
  color: #0f172a;
}

.welcome-text h2 {
  margin: 0 0 10px;
  font-size: clamp(34px, 3.6vw, 42px);
  font-weight: 900;
  line-height: 1.12;
}

.welcome-text p {
  margin: 0;
  font-size: 16px;
  color: #1f2b44;
}

.form-wrap {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e0eaff;
  border-radius: 18px;
  padding: 22px 24px;
  box-shadow: 0 14px 30px rgba(108, 146, 255, 0.16);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.form-wrap:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(108, 146, 255, 0.22), 0 0 26px rgba(94, 168, 255, 0.2);
}

.form-wrap:active {
  transform: translateY(1px);
  box-shadow: 0 10px 20px rgba(108, 146, 255, 0.16);
}

.form-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.form-sub {
  margin: 0;
  color: #6b7280;
  font-size: 13px;
}

.form-title {
  margin: 4px 0 0;
  font-size: 22px;
  color: #0f172a;
}

.back-btn {
  border: 1px solid #d7e8ff;
  background: #f7fbff;
  color: #1f2b44;
  padding: 6px 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.back-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 12px rgba(94, 168, 255, 0.2);
}

.back-btn:active {
  transform: translateY(1px);
  box-shadow: 0 4px 8px rgba(94, 168, 255, 0.14);
}

:deep(.el-form-item__label) {
  color: #1f2937;
  font-weight: 600;
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin: -4px 0 8px;
}

.link {
  color: #2563eb;
  font-size: 14px;
  text-decoration: none;
}

.submit {
  width: 100%;
  height: 44px;
  margin-top: 6px;
  border-radius: 10px;
}

.surface {
  box-shadow: 0 12px 30px rgba(108, 146, 255, 0.12);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.surface:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 26px rgba(108, 146, 255, 0.2), 0 0 24px rgba(94, 168, 255, 0.2);
}

.surface:active {
  transform: translateY(1px);
  box-shadow: 0 10px 18px rgba(108, 146, 255, 0.16);
}

.surface-nocard {
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.surface-nocard:hover {
  transform: translateY(-2px);
}

.surface-nocard:active {
  transform: translateY(1px);
}

.slide-fade-right-enter-active,
.slide-fade-right-leave-active {
  transition: all 0.25s ease;
}
.slide-fade-right-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.slide-fade-right-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}

@media (max-width: 900px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }
  .hero-pane {
    order: -1;
    min-height: 480px;
  }
  .hero-content {
    min-height: 480px;
  }
  .hero-preview {
    position: relative;
    right: auto;
    bottom: auto;
    margin: 0 auto;
    display: block;
    transform: rotate(-1deg);
  }
}

@media (max-width: 768px) {
  .auth-page {
    padding: 20px 12px 28px;
  }
  .top-right-ctrl {
    right: 12px;
    top: 12px;
  }
}
</style>
