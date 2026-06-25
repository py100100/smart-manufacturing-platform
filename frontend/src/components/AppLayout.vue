<template>
  <el-container class="layout">
    <el-aside width="232px" class="layout-aside">
      <div class="brand">
        <div class="brand-mark">MO</div>
        <div>
          <div class="brand-title">制造运营平台</div>
          <div class="brand-subtitle">Manufacturing Operations</div>
        </div>
      </div>

      <div class="aside-section-label">主导航</div>
      <el-menu
        router
        :default-active="$route.path"
        background-color="transparent"
        text-color="#334155"
        active-text-color="#1f4e8c"
        class="side-menu"
      >
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="aside-status">
        <div class="status-row">
          <span class="status-dot" />
          <strong>服务在线</strong>
        </div>
        <span>本地开发环境</span>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <div class="topbar-title">制造运营控制台</div>
          <div class="topbar-subtitle">生产、质量、设备、供应链与工艺闭环管理</div>
        </div>
        <div class="userbox">
          <el-tag type="success" effect="plain">系统正常</el-tag>
          <div class="user-text">
            <strong>{{ user?.username || '用户' }}</strong>
            <span>{{ user?.email || 'local user' }}</span>
          </div>
          <el-button :icon="SwitchButton" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="content">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import {
  Cpu,
  DataAnalysis,
  Histogram,
  Monitor,
  Operation,
  Setting,
  SwitchButton,
  Tickets,
  Timer,
  User,
  Van,
} from '@element-plus/icons-vue';
import { getAuth, logout } from '../api/authApi';
import { useRouter } from 'vue-router';

const router = useRouter();
const user = getAuth();

const navItems = [
  { path: '/dashboard', label: '运营总览', icon: DataAnalysis },
  { path: '/workspace', label: '分析工作台', icon: Cpu },
  { path: '/production', label: '生产调度', icon: Histogram },
  { path: '/quality', label: '质量检测', icon: Tickets },
  { path: '/maintenance', label: '设备监控', icon: Monitor },
  { path: '/supply-chain', label: '供应链管理', icon: Van },
  { path: '/process', label: '工艺优化', icon: Operation },
  { path: '/closure', label: '业务闭环', icon: Setting },
  { path: '/history', label: '历史记录', icon: Timer },
  { path: '/profile', label: '个人中心', icon: User },
];

function handleLogout() {
  logout();
  router.push('/login');
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
}

.layout-aside {
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid #d9e0ea;
  color: #334155;
}

.brand {
  height: 64px;
  padding: 13px 16px;
  border-bottom: 1px solid #e6ebf2;
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: #1f4e8c;
  color: #ffffff;
  font-size: 12px;
  font-weight: 750;
}

.brand-title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.brand-subtitle {
  margin-top: 3px;
  font-size: 11px;
  color: #7b8494;
}

.aside-section-label {
  padding: 14px 16px 6px;
  color: #8a94a6;
  font-size: 12px;
  font-weight: 700;
}

.side-menu {
  border-right: 0;
  padding: 0 10px 12px;
  flex: 1;
}

.side-menu :deep(.el-menu-item) {
  height: 38px;
  margin: 2px 0;
  border-radius: 5px;
}

.side-menu :deep(.el-menu-item:hover) {
  background: #f3f6fa;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: #eef4fb;
  color: #1f4e8c;
  font-weight: 700;
}

.aside-status {
  margin: 12px;
  padding: 12px;
  border: 1px solid #e1e7ef;
  border-radius: 6px;
  background: #f8fafc;
  color: #6b7280;
  font-size: 12px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  color: #111827;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;
  flex: 0 0 auto;
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #d9e0ea;
}

.topbar-title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.topbar-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: #6b7280;
}

.userbox {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-text {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  font-size: 12px;
  color: #6b7280;
}

.user-text strong {
  color: #111827;
}

.content {
  background: #f3f5f8;
  padding: 18px;
}
</style>
