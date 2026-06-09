<template>
  <AppLayout>
    <div class="profile-page">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">个人中心</h1>
          <p class="page-subtitle">账号信息、演示认证状态与本地使用概览</p>
          <div class="head-meta">
            <span>本地认证</span>
            <span>会话状态</span>
            <span>使用概览</span>
          </div>
        </div>
      </div>

      <div class="section-grid">
        <el-card shadow="never" class="panel">
          <template #header><strong>账号信息</strong></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="用户名">{{ user?.username }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ user?.email }}</el-descriptions-item>
            <el-descriptions-item label="登录时间">{{ user?.loggedInAt ? new Date(user.loggedInAt).toLocaleString() : '-' }}</el-descriptions-item>
            <el-descriptions-item label="认证方式">localStorage 本地演示认证</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" class="panel">
          <template #header><strong>使用概览</strong></template>
          <div class="grid-metrics local-grid">
            <div class="panel metric-card">
              <div class="metric-label">历史记录</div>
              <div class="metric-value">{{ historyCount }}</div>
              <div class="metric-foot">浏览器本地保存</div>
            </div>
            <div class="panel metric-card">
              <div class="metric-label">系统角色</div>
              <div class="metric-value">Operator</div>
              <div class="metric-foot">演示操作员</div>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppLayout from '../components/AppLayout.vue';
import { getAuth } from '../api/authApi';
import { getHistory } from '../services/historyService';

const user = getAuth();
const historyCount = computed(() => getHistory().length);
</script>

<style scoped>
.profile-page {
  display: grid;
  gap: 16px;
}

.page-head {
  padding: 22px 24px;
}

.local-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.head-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.head-meta span {
  padding: 5px 9px;
  border: 1px solid rgb(255 255 255 / 0.14);
  border-radius: 6px;
  background: rgb(255 255 255 / 0.07);
  color: #e2e8f0;
  font-size: 12px;
}
</style>
