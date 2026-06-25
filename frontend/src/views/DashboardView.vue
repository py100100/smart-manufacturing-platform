<template>
  <AppLayout>
    <div class="dashboard">
      <div class="panel mvp-strip">
        <div class="mvp-strip__main">
          <div class="mvp-strip__title-row">
            <h3>MVP 演示状态</h3>
            <el-tag :type="mvpStatusType">{{ mvpManifest?.status ?? 'loading' }}</el-tag>
          </div>
          <div class="mvp-health-grid">
            <div v-for="item in healthItems" :key="item.label" class="mvp-health-card">
              <span class="mvp-health-card__label">{{ item.label }}</span>
              <strong :class="{ 'is-ready': item.ready, 'is-down': !item.ready }">
                {{ item.ready ? 'Ready' : 'Check' }}
              </strong>
            </div>
          </div>
        </div>
        <div class="mvp-strip__scenarios">
          <button
            v-for="item in scenarios.slice(0, 5)"
            :key="item.label"
            type="button"
            class="mvp-scenario-button"
            @click="useScenario(item.text)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>

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
          <el-button class="head-action-button" :icon="Refresh" @click="refresh">刷新</el-button>
          <el-button class="head-action-button" :icon="DataLine" @click="seedDemo">一键生成演示数据</el-button>
          <el-button class="head-action-button head-action-button--danger" :icon="Delete" @click="clearAll">
            清空历史
          </el-button>
        </div>
      </div>

      <!-- 智能问答入口 -->
      <div class="panel qa-entry">
        <div class="qa-entry__inner">
          <div class="qa-entry__lead">
            <h3 class="qa-entry__title">智能问答</h3>
            <p class="qa-entry__desc">向智能体提问，获取生产、质量、设备、供应链或工艺方面的分析建议</p>
          </div>
          <div class="qa-entry__form">
            <el-input
              v-model="qaText"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 5 }"
              placeholder="请输入生产、质量、设备、供应链或工艺问题"
              size="large"
              clearable
              @keyup.enter="goAsk"
            />
            <el-button type="primary" size="large" :disabled="!qaText.trim()" @click="goAsk">
              开始分析
            </el-button>
          </div>
          <div class="qa-entry__steps">
            <div class="qa-step">
              <span class="qa-step__num">1</span>
              <span class="qa-step__text">输入工厂业务问题</span>
            </div>
            <span class="qa-step__arrow">&rarr;</span>
            <div class="qa-step">
              <span class="qa-step__num">2</span>
              <span class="qa-step__text">系统自动识别适合的智能体</span>
            </div>
            <span class="qa-step__arrow">&rarr;</span>
            <div class="qa-step">
              <span class="qa-step__num">3</span>
              <span class="qa-step__text">进入工作台执行分析</span>
            </div>
            <span class="qa-step__arrow">&rarr;</span>
            <div class="qa-step">
              <span class="qa-step__num">4</span>
              <span class="qa-step__text">查看结论、依据和后续行动</span>
            </div>
          </div>
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
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { DataLine, Delete, Refresh } from '@element-plus/icons-vue';
import AppLayout from '../components/AppLayout.vue';
import { clearHistory } from '../services/historyService';
import { computeDashboardSummary } from '../services/closureAggregateService';
import { generateDemoHistory, getDemoScenarios } from '../services/demoDataService';
import { fetchMvpManifest, type MvpManifest } from '../api/mvpApi';

const router = useRouter();
const qaText = ref('');
const tick = ref(0);
const mvpManifest = ref<MvpManifest | null>(null);
const summary = computed(() => {
  tick.value;
  return computeDashboardSummary();
});

const mvpStatusType = computed(() => (mvpManifest.value?.status === 'ready' ? 'success' : 'warning'));

const healthItems = computed(() => {
  const health = mvpManifest.value?.health;
  return [
    { label: 'MySQL', ready: Boolean(health?.database_ready) },
    { label: 'DeepSeek', ready: Boolean(health?.model_ready) },
    { label: 'Neo4j', ready: Boolean(health?.graph_ready) },
  ];
});

const scenarios = computed(() => {
  if (mvpManifest.value?.scenarios?.length) {
    return mvpManifest.value.scenarios.map((item) => ({
      label: item.title,
      text: item.request_text,
    }));
  }
  return getDemoScenarios();
});

const metrics = computed(() => [
  { label: '总调用次数', value: summary.value.totalCalls, foot: `今日 ${summary.value.todayCalls} 次` },
  { label: '协同调用', value: summary.value.collaborativeCalls, foot: '跨域问题链式执行' },
  { label: '预警总数', value: summary.value.totalAlerts, foot: `严重 ${summary.value.criticalAlerts} / 警告 ${summary.value.warningAlerts}` },
  { label: '待处理事项', value: summary.value.pendingActions + summary.value.pendingWorkOrders, foot: '工单 + 行动项' },
]);

function goAsk() {
  const q = qaText.value.trim();
  if (!q) return;
  router.push({ path: '/workspace', query: { q } });
}

function useScenario(text: string) {
  qaText.value = text;
  router.push({ path: '/workspace', query: { q: text } });
}

onMounted(async () => {
  try {
    mvpManifest.value = await fetchMvpManifest();
  } catch {
    mvpManifest.value = null;
  }
});

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

.head-actions :deep(.head-action-button) {
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid rgb(15 118 110 / 0.72);
  border-radius: 6px;
  background: linear-gradient(135deg, #2563eb 0%, #0f766e 100%);
  color: #ffffff;
  font-weight: 750;
  box-shadow: 0 12px 24px rgb(37 99 235 / 0.14);
  transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
}

.head-actions :deep(.head-action-button:hover),
.head-actions :deep(.head-action-button:focus) {
  border-color: rgb(15 118 110 / 0.9);
  color: #ffffff;
  filter: brightness(1.04);
  transform: translateY(-1px);
  box-shadow: 0 16px 28px rgb(37 99 235 / 0.18);
}

.head-actions :deep(.head-action-button:active) {
  transform: translateY(0);
}

.head-actions :deep(.head-action-button--danger) {
  border-color: rgb(185 28 28 / 0.72);
  background: linear-gradient(135deg, #dc2626 0%, #b45309 100%);
  box-shadow: 0 12px 24px rgb(220 38 38 / 0.13);
}

.head-actions :deep(.head-action-button--danger:hover),
.head-actions :deep(.head-action-button--danger:focus) {
  border-color: rgb(185 28 28 / 0.9);
  box-shadow: 0 16px 28px rgb(220 38 38 / 0.18);
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

.mvp-strip {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.2fr);
  gap: 18px;
  padding: 18px 22px;
  align-items: center;
}

.mvp-strip__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.mvp-strip__title-row h3 {
  margin: 0;
  font-size: 16px;
  color: #172033;
}

.mvp-health-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.mvp-health-card {
  min-height: 64px;
  padding: 12px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #f8fafc;
}

.mvp-health-card__label {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.mvp-health-card strong {
  display: block;
  margin-top: 7px;
  font-size: 18px;
}

.mvp-health-card strong.is-ready {
  color: #047857;
}

.mvp-health-card strong.is-down {
  color: #b45309;
}

.mvp-strip__scenarios {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.mvp-scenario-button {
  min-height: 64px;
  padding: 10px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
  color: #172033;
  font-size: 13px;
  line-height: 1.35;
  font-weight: 700;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.mvp-scenario-button:hover,
.mvp-scenario-button:focus {
  border-color: #60a5fa;
  box-shadow: 0 10px 20px rgb(37 99 235 / 0.1);
  transform: translateY(-1px);
}

.qa-entry {
  padding: 24px 28px;
}

.qa-entry__inner {
  display: grid;
  grid-template-columns: minmax(220px, 300px) 1fr;
  align-items: start;
  gap: 24px 36px;
}

.qa-entry__lead {
  max-width: 280px;
}

.qa-entry__title {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 700;
  color: #172033;
}

.qa-entry__desc {
  margin: 0;
  font-size: 13px;
  color: #718096;
  line-height: 1.6;
}

.qa-entry__form {
  display: flex;
  gap: 14px;
  align-items: stretch;
  min-width: 0;
}

.qa-entry__form :deep(.el-textarea) {
  flex: 1;
  min-width: 0;
}

.qa-entry__form :deep(.el-textarea__inner) {
  min-height: 96px !important;
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.7;
  resize: vertical;
}

.qa-entry__form .el-button {
  flex-shrink: 0;
  min-width: 116px;
  min-height: 96px;
  font-weight: 700;
}

.qa-entry__steps {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.qa-step {
  display: flex;
  align-items: center;
  gap: 6px;
}

.qa-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.qa-step__text {
  font-size: 12px;
  color: #718096;
  white-space: nowrap;
}

.qa-step__arrow {
  color: #c0c8d4;
  font-size: 12px;
  flex-shrink: 0;
}

@media (max-width: 980px) {
  .mvp-strip {
    grid-template-columns: 1fr;
  }

  .mvp-strip__scenarios {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .qa-entry__inner {
    grid-template-columns: 1fr;
  }

  .qa-entry__lead {
    max-width: none;
  }
}

@media (max-width: 720px) {
  .mvp-health-grid,
  .mvp-strip__scenarios {
    grid-template-columns: 1fr;
  }

  .qa-entry {
    padding: 20px;
  }

  .qa-entry__form {
    flex-direction: column;
  }

  .qa-entry__form .el-button {
    min-height: 44px;
    width: 100%;
  }

  .qa-entry__steps {
    align-items: flex-start;
    flex-direction: column;
  }

  .qa-step__arrow {
    display: none;
  }
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
