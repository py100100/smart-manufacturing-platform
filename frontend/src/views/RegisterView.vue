<template>
  <div class="register-wrap">
    <div class="register-backdrop">
      <div class="eyebrow">Account Provisioning</div>
      <h1>创建企业操作账号</h1>
      <p>账号信息会保存在本地演示环境中，用于验证注册后登录流程。</p>
    </div>
    <el-card class="register-card" shadow="never">
      <template #header>
        <div>
          <div class="eyebrow">Register</div>
          <h2>注册账号</h2>
          <p class="muted">注册后账号会被记住，并可用于后续登录。</p>
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
  grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
  align-items: center;
  justify-content: center;
  gap: 34px;
  background:
    radial-gradient(circle at 80% 18%, rgb(15 118 110 / 0.12), transparent 320px),
    linear-gradient(135deg, #eef3f8 0%, #f8fafc 58%, #e8eef6 100%);
  padding: 42px 56px;
}

.register-backdrop {
  color: #172033;
}

.register-backdrop h1 {
  margin: 16px 0 10px;
  font-size: 34px;
  line-height: 1.2;
}

.register-backdrop p {
  max-width: 460px;
  color: #667085;
  line-height: 1.8;
}

.register-card {
  width: min(520px, 100%);
  border-radius: 8px;
  border-color: #d8e0ea;
  box-shadow: 0 24px 60px rgb(15 23 42 / 0.12);
}

.register-card h2 {
  margin: 8px 0 4px;
}

.eyebrow {
  color: #8ea0bb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.full-btn {
  width: 100%;
  margin-top: 12px;
}

.auth-link {
  margin-top: 18px;
  text-align: center;
  color: #667085;
}

.auth-link a {
  color: #2563eb;
}

@media (max-width: 900px) {
  .register-wrap {
    grid-template-columns: 1fr;
    padding: 24px;
  }

  .register-backdrop {
    display: none;
  }
}
</style>
