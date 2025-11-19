<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'  // ✅ 必须导入
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import AppLogo from '../components/AppLogo.vue'

const router = useRouter()  // ✅ 初始化
const route  = useRoute()   // ✅ 初始化
const store  = useAuthStore()

const active = ref('login')

// 表单 & 校验
const loginForm = reactive({ identifier: '', password: '' })
const loginRules = {
  identifier: [{ required: true, message: '请输入邮箱或用户名', trigger: 'blur' }],
  password:   [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const regForm = reactive({ email: '', username: '', password: '', confirm: '' })
const regRules = {
  email:    [{ required: true, message: '请输入邮箱', trigger: 'blur' },
             { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码（≥6位）', trigger: 'blur' },
             { min: 6, message: '至少 6 位', trigger: 'blur' }],
  confirm:  [{ required: true, message: '请再次输入密码', trigger: 'blur' },
             { validator: (_, v, cb) => v === regForm.password ? cb() : cb(new Error('两次输入不一致')), trigger: 'blur' }],
}

const loginLoading = ref(false)
const regLoading   = ref(false)

// ✅ 模板 ref 要用 ref()，使用时 .value
const loginRef = ref()
const regRef   = ref()

const doLogin = async () => {
  await loginRef.value?.validate(async (ok) => {
    if (!ok) return
    loginLoading.value = true
    try {
      await store.login(loginForm.identifier.trim(), loginForm.password)
      // 这里能在控制台看到 token，便于自检
      console.log('[login] token=', localStorage.getItem('access_token'))
      ElMessage.success('登录成功')
      const redirect = route.query.redirect || '/'
      router.replace(String(redirect))     // ✅ 跳转
    } catch (e) {
      ElMessage.error(e?.response?.data?.error || '登录失败（后端未就绪或网络异常）')
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
      active.value = 'login'
    } catch (e) {
      ElMessage.error(e?.response?.data?.error || '注册失败（后端未就绪或网络异常）')
    } finally {
      regLoading.value = false
    }
  })
}
</script>

<template>
  <div class="page">
    <div class="card">
      <AppLogo />

      <!-- 切换栏：登录 / 注册 -->
      <div class="tabs">
        <button :class="['tab', active==='login' && 'on']" @click="active='login'">登录</button>
        <button :class="['tab', active==='register' && 'on']" @click="active='register'">注册</button>
      </div>

      <!-- 登录面板 -->
      <el-form ref="loginRef" :model="loginForm" :rules="loginRules" label-width="120px" v-show="active==='login'">
        <el-form-item label="邮箱 / 用户名" prop="identifier">
          <el-input v-model="loginForm.identifier" placeholder="请输入邮箱或用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>

        <div class="actions">
          <a class="link" href="javascript:;">忘记密码？</a>
        </div>

        <el-button type="primary" class="submit" :loading="loginLoading" @click="doLogin">登录</el-button>
      </el-form>

      <!-- 注册面板 -->
      <el-form ref="regRef" :model="regForm" :rules="regRules" label-width="120px" v-show="active==='register'">
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="regForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="regForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="regForm.password" type="password" placeholder="请输入密码（至少6位）" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="regForm.confirm" type="password" placeholder="请再次输入密码" show-password />
        </el-form-item>

        <el-button type="primary" class="submit" :loading="regLoading" @click="doRegister">注册</el-button>
      </el-form>
    </div>

    <footer class="footer">
      © 2025 Designed by hyk · 用心记录每一份美好~
    </footer>
  </div>
</template>

<style scoped>
/* 页面浅灰背景，居中卡片 */
.page {
  min-height: 100vh;
  background: #f6f8fb;
  display: grid;
  grid-template-rows: 1fr auto;
}

/* 卡片容器：居中、阴影与圆角 */
.card {
  width: 520px;
  margin: 6vh auto 2vh;
  padding: 34px 36px 28px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(43, 47, 54, 0.08);
}

/* 顶部切换 Tab：贴近你的示意图 */
.tabs {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
  margin: 22px 0 12px;
  background: #f2f5fb; border-radius: 12px; padding: 6px;
}
.tab {
  border: none; background: transparent; padding: 10px 0;
  border-radius: 10px; font-weight: 600; color:#6b7280; cursor:pointer;
}
.tab.on {
  background: #ffffff;
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.12);
  color: #2563eb;
}

/* 表单与按钮 */
:deep(.el-form-item__label) { color:#374151; }
.actions { display:flex; justify-content:flex-end; margin: -6px 0 8px; }
.link { color:#2563eb; font-size: 14px; text-decoration: none; }
.submit {
  width: 100%;
  height: 40px;
  margin-top: 4px;
  border-radius: 8px;
}

/* 页脚 */
.footer {
  text-align:center; color:#9aa0a6; padding: 18px 0 24px;
}
</style>
