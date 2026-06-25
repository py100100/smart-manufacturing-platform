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
  gap: 14px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
}

.detail-result {
  margin-top: 16px;
}

.history-clear-button {
  min-height: 36px;
  padding: 0 14px;
  border-color: #f3b6ad;
  border-radius: 5px;
  background: #ffffff;
  color: #b42318;
  font-weight: 650;
}

.history-clear-button:hover,
.history-clear-button:focus {
  border-color: #e58b7f;
  color: #8f1f14;
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
