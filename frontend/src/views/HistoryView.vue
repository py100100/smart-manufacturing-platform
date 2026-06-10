<template>
  <AppLayout>
    <div class="history-page">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">历史记录</h1>
          <p class="page-subtitle">查看每次智能体执行的请求、决策、证据和闭环输出</p>
          <div class="head-meta">
            <span>执行留痕</span>
            <span>证据可查</span>
            <span>闭环可回放</span>
          </div>
        </div>
        <el-button class="history-clear-button" @click="clearAll">清空历史</el-button>
      </div>

      <div class="two-col">
        <el-card shadow="never" class="panel">
          <template #header><strong>执行列表</strong></template>
          <el-table :data="history" height="620" highlight-current-row @row-click="selected = $event">
            <el-table-column prop="agentName" label="智能体" width="220" />
            <el-table-column prop="decision" label="决策" />
            <el-table-column label="时间" width="180">
              <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="panel">
          <template #header><strong>记录详情</strong></template>
          <div v-if="selected">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="请求">{{ selected.requestText }}</el-descriptions-item>
              <el-descriptions-item label="摘要">{{ selected.summary }}</el-descriptions-item>
              <el-descriptions-item label="决策">{{ selected.decision }}</el-descriptions-item>
              <el-descriptions-item label="模式">{{ selected.mode }}</el-descriptions-item>
            </el-descriptions>
            <AgentResult class="detail-result" :result="selected.result" />
          </div>
          <el-empty v-else description="请选择一条历史记录" />
        </el-card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import AppLayout from '../components/AppLayout.vue';
import AgentResult from '../components/AgentResult.vue';
import type { HistoryEntry } from '../types/agent';
import { clearHistory, getHistory } from '../services/historyService';

const history = ref<HistoryEntry[]>(getHistory());
const selected = ref<HistoryEntry | null>(history.value[0] ?? null);

function formatTime(value: string) {
  return new Date(value).toLocaleString();
}

async function clearAll() {
  await ElMessageBox.confirm('确认清空全部历史记录？', '清空历史', { type: 'warning' });
  clearHistory();
  history.value = [];
  selected.value = null;
  ElMessage.success('已清空');
}
</script>

<style scoped>
.history-page {
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

.detail-result {
  margin-top: 16px;
}

.history-clear-button {
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid rgb(185 28 28 / 0.72);
  border-radius: 6px;
  background: linear-gradient(135deg, #dc2626 0%, #b45309 100%);
  color: #ffffff;
  font-weight: 750;
  box-shadow: 0 12px 24px rgb(220 38 38 / 0.13);
  transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
}

.history-clear-button:hover,
.history-clear-button:focus {
  border-color: rgb(185 28 28 / 0.9);
  color: #ffffff;
  filter: brightness(1.04);
  transform: translateY(-1px);
  box-shadow: 0 16px 28px rgb(220 38 38 / 0.18);
}

.history-clear-button:active {
  transform: translateY(0);
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
