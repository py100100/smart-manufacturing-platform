<template>
  <el-container class="layout">
    <el-aside width="248px" class="layout-aside">
      <div class="brand">
        <div class="brand-mark">IM</div>
        <div>
          <div class="brand-title">智能制造平台</div>
          <div class="brand-subtitle">Manufacturing OS</div>
        </div>
      </div>
      <div class="aside-status">
        <span class="status-dot" />
        <div>
          <strong>生产运营在线</strong>
          <span>Agentic RAG 已接入</span>
        </div>
      </div>
      <el-menu
        router
        :default-active="$route.path"
        background-color="transparent"
        text-color="#cbd5e1"
        active-text-color="#ffffff"
        class="side-menu"
      >
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <div class="topbar-title">制造运营控制台</div>
          <div class="topbar-subtitle">统一监控 · 智能分析 · 闭环追踪</div>
        </div>
        <div class="userbox">
          <el-tag type="success" effect="light">系统正常</el-tag>
          <div class="user-text">
            <strong>{{ user?.username || '用户' }}</strong>
            <span>{{ user?.email || 'local user' }}</span>
          </div>
          <el-button :icon="SwitchButton" @click="handleLogout">退出登录</el-button>
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
  { path: '/workspace', label: '智能体工作台', icon: Cpu },
  { path: '/production', label: '生产调度看板', icon: Histogram },
  { path: '/quality', label: '质量检测中心', icon: Tickets },
  { path: '/maintenance', label: '设备监控面板', icon: Monitor },
  { path: '/supply-chain', label: '供应链管理', icon: Van },
  { path: '/process', label: '工艺优化分析', icon: Operation },
  { path: '/closure', label: '业务闭环中心', icon: Setting },
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
  background:
    linear-gradient(180deg, #111827 0%, #172033 56%, #101827 100%);
  color: #fff;
  box-shadow: 8px 0 28px rgb(15 23 42 / 0.18);
}

.brand {
  height: 64px;
  padding: 13px 18px;
  border-bottom: 1px solid rgb(255 255 255 / 0.1);
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563eb 0%, #0f766e 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 10px 20px rgb(37 99 235 / 0.24);
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
}

.brand-subtitle {
  margin-top: 4px;
  font-size: 11px;
  color: #9aa7ba;
}

.aside-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 14px 10px;
  padding: 12px;
  border: 1px solid rgb(255 255 255 / 0.1);
  border-radius: 8px;
  background: rgb(255 255 255 / 0.05);
}

.aside-status strong,
.aside-status span {
  display: block;
}

.aside-status strong {
  font-size: 12px;
  color: #f8fafc;
}

.aside-status span {
  margin-top: 3px;
  font-size: 11px;
  color: #94a3b8;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 4px rgb(34 197 94 / 0.14);
  flex: 0 0 auto;
}

.side-menu {
  border-right: 0;
  padding: 4px 10px 16px;
}

.side-menu :deep(.el-menu-item) {
  height: 42px;
  margin: 4px 0;
  border-radius: 7px;
}

.side-menu :deep(.el-menu-item:hover) {
  background: rgb(255 255 255 / 0.08);
}

.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #2563eb 0%, #0f766e 100%);
  box-shadow: 0 10px 20px rgb(15 23 42 / 0.22);
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgb(255 255 255 / 0.94);
  border-bottom: 1px solid #dbe3ee;
  backdrop-filter: blur(10px);
}

.topbar-title {
  font-size: 15px;
  font-weight: 650;
  color: #172033;
}

.topbar-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: #8a94a6;
}

.userbox {
  display: flex;
  align-items: center;
  gap: 14px;
}

.user-text {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  font-size: 12px;
  color: #667085;
}

.user-text strong {
  color: #172033;
}

.content {
  background:
    linear-gradient(rgb(15 23 42 / 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgb(15 23 42 / 0.035) 1px, transparent 1px),
    linear-gradient(180deg, #f5f7fb 0%, #eef2f7 100%);
  background-size: 28px 28px, 28px 28px, auto;
  padding: 22px;
}
</style>
