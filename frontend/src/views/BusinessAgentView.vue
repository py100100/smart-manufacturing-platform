<template>
  <AppLayout>
    <div class="business-page">
      <div class="panel page-head">
        <div>
          <h1 class="page-title">{{ page.title }}</h1>
          <p class="page-subtitle">{{ page.subtitle }}</p>
          <div class="head-meta">
            <span>指定智能体</span>
            <span>结构化输出</span>
            <span>业务闭环联动</span>
          </div>
        </div>
        <el-tag size="large" effect="dark">{{ page.agentLabel }}</el-tag>
      </div>

      <div class="grid-metrics">
        <div v-for="m in metrics" :key="m.label" class="panel metric-card">
          <div class="metric-label">{{ m.label }}</div>
          <div class="metric-value">{{ m.value }}</div>
          <div class="metric-foot">{{ m.foot }}</div>
        </div>
      </div>

      <el-card shadow="never" class="panel">
        <template #header><strong>业务分析</strong></template>
        <el-input v-model="requestText" type="textarea" :rows="5" />
        <div class="action-row">
          <el-button @click="requestText = page.sample">填入示例</el-button>
          <el-button type="primary" :loading="loading" @click="run">调用 {{ page.agentLabel }}</el-button>
        </div>
      </el-card>

      <AgentResult :result="result" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import AppLayout from '../components/AppLayout.vue';
import AgentResult from '../components/AgentResult.vue';
import type { AgentExecutionResponse } from '../types/agent';
import { executeNamedAgent } from '../api/agentApi';
import { saveHistory } from '../services/historyService';

interface PageMeta {
  title: string;
  subtitle: string;
  agentName: string;
  agentLabel: string;
  sample: string;
}

const route = useRoute();
const page = computed(() => route.meta.page as PageMeta);
const requestText = ref('');
const loading = ref(false);
const result = ref<AgentExecutionResponse | null>(null);

watch(
  page,
  (value) => {
    requestText.value = value.sample;
    result.value = null;
  },
  { immediate: true },
);

const metrics = computed(() => [
  { label: '智能体', value: page.value.agentLabel, foot: '指定调用' },
  { label: '执行模式', value: 'Direct', foot: '跳过自动路由' },
  { label: '闭环输出', value: result.value ? '已生成' : '待分析', foot: '预警/工单/报告/行动项' },
  { label: '节点反馈', value: result.value?.node_feedback?.length || 0, foot: '可追溯执行过程' },
]);

async function run() {
  if (!requestText.value.trim()) {
    ElMessage.warning('请输入业务问题');
    return;
  }
  loading.value = true;
  try {
    result.value = await executeNamedAgent(page.value.agentName, {
      request_text: requestText.value.trim(),
      require_llm: false,
    });
    saveHistory({
      mode: result.value.execution_mode,
      agentName: result.value.agent_name,
      requestText: result.value.request_text,
      summary: result.value.summary,
      decision: result.value.decision,
      result: result.value,
    });
    ElMessage.success('分析完成');
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '执行失败');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.business-page {
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

.action-row {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
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
