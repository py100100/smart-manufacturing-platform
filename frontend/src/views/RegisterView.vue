<template>
  <div class="register-wrap">
    <aside class="register-info">
      <div class="brand-row">
        <div class="brand-mark">MO</div>
        <div>
          <strong>制造运营平台</strong>
          <span>Account Provisioning</span>
        </div>
      </div>
      <div>
        <h1>创建企业操作账号</h1>
        <p>账号用于本地演示环境登录和会话识别，方便验证完整的注册、登录和业务操作流程。</p>
      </div>
    </aside>

    <main class="register-main">
      <el-card class="register-card" shadow="never">
        <template #header>
          <div>
            <span class="eyebrow">Register</span>
            <h2>注册账号</h2>
            <p class="muted">注册后可直接进入制造运营控制台。</p>
          </div>
        </template>
        <el-form label-position="top">
          <el-form-item label="用户名">
            <el-input v-model="username" size="large" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="email" size="large" placeholder="选填" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="password" size="large" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认密码">
            <el-input v-model="confirmPassword" size="large" type="password" show-password />
          </el-form-item>
          <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
          <el-button class="full-btn" type="primary" size="large" :loading="loading" @click="handleRegister">
            注册
          </el-button>
        </el-form>
        <div class="auth-link">
          已有账号？
          <router-link to="/login">登录</router-link>
        </div>
      </el-card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { register } from '../api/authApi';

const router = useRouter();
const username = ref('');
const email = ref('');
const password = ref('');
const confirmPassword = ref('');
const loading = ref(false);
const error = ref('');

function handleRegister() {
  error.value = '';
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致';
    return;
  }
  loading.value = true;
  try {
    register(username.value, password.value, email.value);
    router.push('/dashboard');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '注册失败';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.register-wrap {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(420px, 1fr);
  background: #f3f5f8;
}

.register-info {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 40px;
  background: #172033;
  color: #ffffff;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-row strong,
.brand-row span {
  display: block;
}

.brand-row strong {
  font-size: 16px;
}

.brand-row span {
  margin-top: 3px;
  color: #aeb9c9;
  font-size: 12px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
  font-size: 13px;
  font-weight: 800;
}

.register-info h1 {
  margin: 0 0 12px;
  font-size: 30px;
  line-height: 1.25;
}

.register-info p {
  max-width: 320px;
  margin: 0;
  color: #cbd5e1;
  line-height: 1.75;
  font-size: 14px;
}

.register-main {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

.register-card {
  width: min(460px, 100%);
  border-radius: 6px;
  border-color: #d9e0ea;
  box-shadow: 0 12px 28px rgb(16 24 40 / 0.08);
}

.register-card :deep(.el-card__header) {
  padding: 24px 28px 18px;
  border-bottom: 1px solid #edf1f7;
}

.register-card :deep(.el-card__body) {
  padding: 24px 28px 28px;
}

.register-card h2 {
  margin: 8px 0 4px;
  color: #111827;
  font-size: 24px;
}

.eyebrow {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}

.full-btn {
  width: 100%;
  margin-top: 10px;
}

.auth-link {
  margin-top: 18px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}

.auth-link a {
  color: #1f4e8c;
  font-weight: 650;
}

@media (max-width: 860px) {
  .register-wrap {
    grid-template-columns: 1fr;
  }

  .register-info {
    display: none;
  }
}
</style>
