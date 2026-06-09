<template>
  <AppLayout>
    <div class="dashboard">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">运营总览</h1>
          <p class="page-subtitle">工厂风险、工单、智能体调用与业务闭环的管理视图</p>
          <div class="head-meta">
            <span>实时运营</span>
            <span>5 个智能体在线</span>
            <span>闭环对象自动汇总</span>
          </div>
        </div>
        <div class="head-actions">
          <el-button :icon="Refresh" @click="refresh">刷新</el-button>
          <el-button type="primary" :icon="DataLine" @click="seedDemo">一键生成演示数据</el-button>
          <el-button type="danger" plain :icon="Delete" @click="clearAll">清空历史</el-button>
        </div>
      </div>

      <div class="grid-metrics">
        <div v-for="m in metrics" :key="m.label" class="panel metric-card">
          <div class="metric-label">{{ m.label }}</div>
          <div class="metric-value">{{ m.value }}</div>
          <div class="metric-foot">{{ m.foot }}</div>
        </div>
      </div>

      <div class="section-grid">
        <el-card shadow="never" class="panel">
          <template #header><strong>风险概览</strong></template>
          <el-table :data="summary.recentAlerts" height="260">
            <el-table-column prop="title" label="预警" min-width="160" />
            <el-table-column label="等级" width="90">
              <template #default="{ row }">
                <el-tag :type="severityType(row.severity)">{{ row.severity }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_agent" label="来源" width="170" />
          </el-table>
        </el-card>

        <el-card shadow="never" class="panel">
          <template #header><strong>智能体运行分布</strong></template>
          <div v-if="summary.agentUsage.length">
            <div v-for="item in summary.agentUsage" :key="item.name" class="usage-row">
              <span>{{ item.displayName }}</span>
              <el-progress :percentage="usagePercent(item.count)" :stroke-width="10" />
              <strong>{{ item.count }}</strong>
            </div>
          </div>
          <el-empty v-else description="暂无智能体运行记录" />
        </el-card>
      </div>

      <div class="section-grid">
        <el-card shadow="never" class="panel">
          <template #header><strong>最近工单</strong></template>
          <el-table :data="summary.recentWorkOrders" height="250">
            <el-table-column prop="title" label="工单" />
            <el-table-column prop="priority" label="优先级" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
          </el-table>
        </el-card>
        <el-card shadow="never" class="panel">
          <template #header><strong>行动项</strong></template>
          <el-table :data="summary.recentActions" height="250">
            <el-table-column prop="description" label="事项" />
            <el-table-column prop="priority" label="优先级" width="100" />
            <el-table-column prop="status" label="状态" width="110" />
          </el-table>
        </el-card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { DataLine, Delete, Refresh } from '@element-plus/icons-vue';
import AppLayout from '../components/AppLayout.vue';
import { clearHistory } from '../services/historyService';
import { computeDashboardSummary } from '../services/closureAggregateService';
import { generateDemoHistory } from '../services/demoDataService';

const tick = ref(0);
const summary = computed(() => {
  tick.value;
  return computeDashboardSummary();
});

const metrics = computed(() => [
  { label: '总调用次数', value: summary.value.totalCalls, foot: `今日 ${summary.value.todayCalls} 次` },
  { label: '协同调用', value: summary.value.collaborativeCalls, foot: '跨域问题链式执行' },
  { label: '预警总数', value: summary.value.totalAlerts, foot: `严重 ${summary.value.criticalAlerts} / 警告 ${summary.value.warningAlerts}` },
  { label: '待处理事项', value: summary.value.pendingActions + summary.value.pendingWorkOrders, foot: '工单 + 行动项' },
]);

function refresh() {
  tick.value++;
}

function seedDemo() {
  const count = generateDemoHistory();
  refresh();
  ElMessage.success(`已生成 ${count} 条演示记录`);
}

async function clearAll() {
  await ElMessageBox.confirm('确认清空全部历史记录？', '清空历史', { type: 'warning' });
  clearHistory();
  refresh();
  ElMessage.success('历史记录已清空');
}

function severityType(severity: string) {
  if (severity === 'critical') return 'danger';
  if (severity === 'warning') return 'warning';
  return 'info';
}

function usagePercent(count: number) {
  const max = Math.max(...summary.value.agentUsage.map((item) => item.count), 1);
  return Math.round((count / max) * 100);
}
</script>

<style scoped>
.dashboard {
  display: grid;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px;
}

.head-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
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

.usage-row {
  display: grid;
  grid-template-columns: 110px 1fr 36px;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  font-size: 13px;
}
</style>
