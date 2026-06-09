<template>
  <div class="auth-page">
    <section class="auth-hero">
      <div>
        <div class="eyebrow">Manufacturing Operations Center</div>
        <h1>智能制造服务平台</h1>
        <p>面向生产、质量、设备、供应链与工艺团队的统一运营后台。</p>
      </div>
      <div class="hero-stats">
        <span><strong>5</strong> 智能体</span>
        <span><strong>RAG</strong> 检索</span>
        <span><strong>4</strong> 闭环对象</span>
      </div>
    </section>

    <section class="auth-card">
      <div class="card-topline">
        <span class="security-dot" />
        <span>Enterprise Access</span>
      </div>
      <div class="card-title-row">
        <div>
          <div class="eyebrow">Secure Sign In</div>
          <h2>账号登录</h2>
          <p class="muted">请输入已授权账号完成身份验证。</p>
        </div>
        <div class="login-badge">OPS</div>
      </div>
      <el-form class="auth-form" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="username" size="large" placeholder="输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" size="large" type="password" show-password placeholder="输入密码" />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
        <el-button type="primary" size="large" class="full-btn" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>
      <div class="security-strip">
        <span>本地演示认证</span>
        <span>会话状态持久化</span>
        <span>权限入口校验</span>
      </div>
      <div class="auth-link">
        还没有账号？
        <router-link to="/register">注册</router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { login } from '../api/authApi';

const router = useRouter();
const username = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');

function handleLogin() {
  error.value = '';
  loading.value = true;
  try {
    login(username.value, password.value);
    router.push('/dashboard');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 1.1fr) minmax(380px, 0.9fr);
  align-items: stretch;
  background:
    radial-gradient(circle at 18% 18%, rgb(37 99 235 / 0.14), transparent 330px),
    linear-gradient(135deg, #eef3f8 0%, #f8fafc 52%, #e8eef6 100%);
}

.auth-hero {
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgb(17 24 39 / 0.96), rgb(23 32 51 / 0.98)),
    repeating-linear-gradient(90deg, transparent 0, transparent 48px, rgb(255 255 255 / 0.04) 49px);
  color: #fff;
  padding: 56px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.auth-hero::after {
  content: "";
  position: absolute;
  right: -120px;
  bottom: -130px;
  width: 360px;
  height: 360px;
  border: 1px solid rgb(255 255 255 / 0.1);
  border-radius: 50%;
  box-shadow: inset 0 0 0 42px rgb(255 255 255 / 0.03);
}

.auth-hero h1 {
  margin: 18px 0 12px;
  font-size: 38px;
  line-height: 1.2;
}

.auth-hero p {
  max-width: 520px;
  color: #cbd5e1;
  line-height: 1.8;
}

.eyebrow {
  color: #8ea0bb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.hero-stats {
  display: flex;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.hero-stats span {
  border: 1px solid rgb(255 255 255 / 0.14);
  border-radius: 8px;
  padding: 10px 14px;
  background: rgb(255 255 255 / 0.06);
  color: #d6deeb;
}

.hero-stats strong {
  color: #ffffff;
}

.auth-card {
  position: relative;
  overflow: hidden;
  align-self: center;
  width: min(440px, calc(100% - 48px));
  margin: 0 auto;
  padding: 36px;
  background:
    linear-gradient(180deg, rgb(255 255 255 / 0.98) 0%, rgb(248 250 252 / 0.98) 100%);
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  box-shadow: 0 24px 60px rgb(15 23 42 / 0.12);
}

.auth-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 4px;
  background: linear-gradient(90deg, #2563eb 0%, #0f766e 55%, #94a3b8 100%);
}

.auth-card::after {
  content: "";
  position: absolute;
  right: -42px;
  top: -42px;
  width: 130px;
  height: 130px;
  border: 1px solid rgb(37 99 235 / 0.12);
  border-radius: 50%;
  box-shadow: inset 0 0 0 24px rgb(15 118 110 / 0.04);
  pointer-events: none;
}

.card-topline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 9px;
  border: 1px solid #d8e0ea;
  border-radius: 6px;
  background: #f8fafc;
  color: #475467;
  font-size: 12px;
  font-weight: 650;
}

.security-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 4px rgb(34 197 94 / 0.12);
}

.card-title-row {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  margin-top: 20px;
}

.login-badge {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #172033;
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 14px 28px rgb(15 23 42 / 0.18);
}

.auth-card h2 {
  margin: 10px 0 4px;
  color: #172033;
}

.auth-form {
  position: relative;
  z-index: 1;
  margin-top: 24px;
}

.full-btn {
  width: 100%;
  margin-top: 12px;
  height: 42px;
}

.security-strip {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 18px;
}

.security-strip span {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  border: 1px solid #e1e7ef;
  border-radius: 6px;
  background: #fbfdff;
  color: #667085;
  font-size: 11px;
  text-align: center;
}

.auth-link {
  position: relative;
  z-index: 1;
  margin-top: 18px;
  text-align: center;
  color: #667085;
}

.auth-link a {
  color: #2563eb;
}

@media (max-width: 900px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-hero {
    display: none;
  }

  .security-strip {
    grid-template-columns: 1fr;
  }
}
</style>
