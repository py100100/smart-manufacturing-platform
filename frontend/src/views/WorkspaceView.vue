<template>
  <AppLayout>
    <div class="workspace">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">智能体工作台</h1>
          <p class="page-subtitle">支持自动路由、指定智能体调用和多智能体协同分析</p>
          <div class="head-meta">
            <span>自动路由</span>
            <span>链式协同</span>
            <span>节点反馈可追溯</span>
          </div>
        </div>
      </div>

      <div class="two-col">
        <el-card shadow="never" class="panel">
          <template #header><strong>分析请求</strong></template>
          <el-form label-position="top">
            <el-form-item label="智能体模式">
              <el-select v-model="selectedAgent" clearable placeholder="自动路由">
                <el-option v-for="a in agents" :key="a.name" :label="a.display_name" :value="a.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="业务问题">
              <el-input
                v-model="requestText"
                type="textarea"
                :rows="8"
                placeholder="输入生产、质量、设备、供应链或工艺问题"
              />
            </el-form-item>
            <div class="scenario-buttons">
              <el-button v-for="item in scenarios" :key="item.label" size="small" @click="requestText = item.text">
                {{ item.label }}
              </el-button>
            </div>
            <el-button type="primary" size="large" :loading="loading" @click="run">
              执行分析
            </el-button>
          </el-form>
        </el-card>

        <el-card shadow="never" class="panel">
          <template #header><strong>可用智能体</strong></template>
          <el-table :data="agents" height="430">
            <el-table-column prop="display_name" label="名称" width="160" />
            <el-table-column prop="scenario_hint" label="适用场景" />
          </el-table>
        </el-card>
      </div>

      <AgentResult :result="result" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import AppLayout from '../components/AppLayout.vue';
import AgentResult from '../components/AgentResult.vue';
import type { AgentExecutionResponse, AgentMeta } from '../types/agent';
import { executeAgent, executeNamedAgent, fetchAgentList } from '../api/agentApi';
import { saveHistory } from '../services/historyService';
import { getDemoScenarios } from '../services/demoDataService';

const agents = ref<AgentMeta[]>([]);
const selectedAgent = ref('');
const requestText = ref('质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率');
const loading = ref(false);
const result = ref<AgentExecutionResponse | null>(null);
const scenarios = getDemoScenarios();

onMounted(async () => {
  try {
    agents.value = await fetchAgentList();
  } catch {
    agents.value = [];
  }
});

async function run() {
  if (!requestText.value.trim()) {
    ElMessage.warning('请输入业务问题');
    return;
  }
  loading.value = true;
  try {
    const body = { request_text: requestText.value.trim(), require_llm: false };
    result.value = selectedAgent.value
      ? await executeNamedAgent(selectedAgent.value, body)
      : await executeAgent(body);
    saveHistory({
      mode: result.value.execution_mode,
      agentName: result.value.agent_name,
      requestText: result.value.request_text,
      summary: result.value.summary,
      decision: result.value.decision,
      result: result.value,
    });
    ElMessage.success('分析完成，已写入历史记录');
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '执行失败');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.workspace {
  display: grid;
  gap: 16px;
}

.page-head {
  padding: 22px 24px;
}

.scenario-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
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

.scenario-buttons :deep(.el-button) {
  border-color: #d8e0ea;
  background: #f8fafc;
}
</style>
