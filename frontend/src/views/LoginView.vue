<template>
  <div class="auth-page">
    <aside class="auth-info">
      <div class="brand-row">
        <div class="brand-mark">MO</div>
        <div>
          <strong>制造运营平台</strong>
          <span>Manufacturing Operations</span>
        </div>
      </div>

      <div class="system-summary">
        <h1>企业运营控制台</h1>
        <p>面向生产、质量、设备、供应链和工艺团队的统一业务分析与闭环管理入口。</p>
      </div>

      <dl class="info-list">
        <div>
          <dt>覆盖范围</dt>
          <dd>五大制造业务域</dd>
        </div>
        <div>
          <dt>运行模式</dt>
          <dd>本地演示环境</dd>
        </div>
        <div>
          <dt>数据能力</dt>
          <dd>RAG / 知识图谱 / 业务闭环</dd>
        </div>
      </dl>
    </aside>

    <main class="auth-main">
      <section class="auth-card">
        <div class="card-heading">
          <span class="eyebrow">Enterprise Access</span>
          <h2>账号登录</h2>
          <p>请输入已授权账号进入制造运营控制台。</p>
        </div>

        <el-form class="auth-form" label-position="top" @submit.prevent>
          <el-form-item label="用户名">
            <el-input v-model="username" size="large" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="password"
              size="large"
              type="password"
              show-password
              placeholder="请输入密码"
            />
          </el-form-item>
          <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
          <el-button type="primary" size="large" class="full-btn" :loading="loading" @click="handleLogin">
            登录
          </el-button>
        </el-form>

        <div class="auth-meta">
          <span>本地认证</span>
          <span>会话保持</span>
          <span>操作留痕</span>
        </div>

        <div class="auth-link">
          还没有账号？
          <router-link to="/register">注册</router-link>
        </div>
      </section>
    </main>
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
  grid-template-columns: minmax(320px, 420px) minmax(420px, 1fr);
  background: #f3f5f8;
}

.auth-info {
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

.system-summary h1 {
  margin: 0 0 12px;
  font-size: 30px;
  line-height: 1.25;
  letter-spacing: 0;
}

.system-summary p {
  max-width: 320px;
  margin: 0;
  color: #cbd5e1;
  line-height: 1.75;
  font-size: 14px;
}

.info-list {
  display: grid;
  gap: 12px;
  margin: 0;
}

.info-list div {
  padding: 12px 0;
  border-top: 1px solid rgb(255 255 255 / 0.12);
}

.info-list dt {
  color: #9fb0c5;
  font-size: 12px;
}

.info-list dd {
  margin: 5px 0 0;
  font-size: 14px;
  font-weight: 650;
}

.auth-main {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

.auth-card {
  width: min(420px, 100%);
  padding: 32px;
  background: #ffffff;
  border: 1px solid #d9e0ea;
  border-radius: 6px;
  box-shadow: 0 12px 28px rgb(16 24 40 / 0.08);
}

.card-heading {
  margin-bottom: 22px;
}

.eyebrow {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}

.card-heading h2 {
  margin: 8px 0 6px;
  color: #111827;
  font-size: 24px;
}

.card-heading p {
  margin: 0;
  color: #6b7280;
  font-size: 13px;
}

.full-btn {
  width: 100%;
  margin-top: 10px;
  height: 42px;
}

.auth-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #edf1f7;
  color: #7b8494;
  font-size: 12px;
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
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-info {
    display: none;
  }
}
</style>
