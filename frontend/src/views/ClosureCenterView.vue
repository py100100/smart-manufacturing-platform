<template>
  <AppLayout>
    <div class="closure-page">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">业务闭环中心</h1>
          <p class="page-subtitle">汇总所有智能体产生的预警、工单、报告和行动项</p>
          <div class="head-meta">
            <span>预警</span>
            <span>工单</span>
            <span>报告</span>
            <span>行动项</span>
          </div>
        </div>
        <el-input v-model="keyword" clearable placeholder="搜索闭环记录" class="search" />
      </div>

      <el-tabs class="panel tabs" type="border-card">
        <el-tab-pane label="预警">
          <el-table :data="filteredAlerts" height="560">
            <el-table-column prop="title" label="标题" />
            <el-table-column prop="message" label="内容" min-width="260" />
            <el-table-column label="等级" width="100">
              <template #default="{ row }">
                <el-tag :type="severityType(row.severity)">{{ row.severity }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_agent" label="来源" width="190" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="工单">
          <el-table :data="filteredOrders" height="560">
            <el-table-column prop="title" label="工单" />
            <el-table-column prop="description" label="描述" min-width="260" />
            <el-table-column prop="priority" label="优先级" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="报告">
          <el-table :data="filteredReports" height="560">
            <el-table-column prop="title" label="报告" />
            <el-table-column prop="summary" label="摘要" min-width="300" />
            <el-table-column label="来源" width="220">
              <template #default="{ row }">{{ row.source_agents?.join(' / ') }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="行动项">
          <el-table :data="filteredActions" height="560">
            <el-table-column prop="description" label="行动项" min-width="300" />
            <el-table-column prop="priority" label="优先级" width="100" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column prop="source_agent" label="来源" width="190" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import AppLayout from '../components/AppLayout.vue';
import {
  getAllActions,
  getAllAlerts,
  getAllReports,
  getAllWorkOrders,
} from '../services/closureAggregateService';

const keyword = ref('');
const alerts = computed(() => getAllAlerts());
const orders = computed(() => getAllWorkOrders());
const reports = computed(() => getAllReports());
const actions = computed(() => getAllActions());

function matchText(value: unknown) {
  const text = JSON.stringify(value).toLowerCase();
  return text.includes(keyword.value.trim().toLowerCase());
}

const filteredAlerts = computed(() => alerts.value.filter(matchText));
const filteredOrders = computed(() => orders.value.filter(matchText));
const filteredReports = computed(() => reports.value.filter(matchText));
const filteredActions = computed(() => actions.value.filter(matchText));

function severityType(severity: string) {
  if (severity === 'critical') return 'danger';
  if (severity === 'warning') return 'warning';
  return 'info';
}
</script>

<style scoped>
.closure-page {
  display: grid;
  gap: 14px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
}

.search {
  width: 280px;
}

.tabs {
  overflow: hidden;
}

.head-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.head-meta span {
  padding: 5px 9px;
  border: 1px solid #d9e0ea;
  border-radius: 4px;
  background: #f8fafc;
  color: #5b6678;
  font-size: 12px;
}
</style>
