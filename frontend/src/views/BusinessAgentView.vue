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

      <div class="grid-metrics business-metrics">
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

      <AgentResult v-if="result" :result="result" />
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
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px;
  border-color: #d8e0ea;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 14px 32px rgb(15 23 42 / 0.07);
}

.page-head::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgb(37 99 235 / 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgb(37 99 235 / 0.035) 1px, transparent 1px);
  background-size: 32px 32px;
  pointer-events: none;
}

.page-head::after {
  content: "";
  position: absolute;
  right: 28px;
  top: 20px;
  width: 150px;
  height: 64px;
  border-top: 1px solid rgb(37 99 235 / 0.16);
  border-right: 1px solid rgb(37 99 235 / 0.16);
  pointer-events: none;
}

.page-head > * {
  position: relative;
  z-index: 1;
}

.page-head .page-title {
  color: #111827;
}

.page-head .page-subtitle {
  color: #667085;
}

.page-head :deep(.el-tag) {
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #0f766e 100%);
  box-shadow: 0 10px 20px rgb(37 99 235 / 0.16);
}

.business-metrics {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.business-metrics .metric-card {
  min-width: 0;
}

.business-metrics .metric-value {
  font-size: 26px;
  line-height: 1.18;
  overflow-wrap: anywhere;
}

.business-metrics .metric-foot {
  line-height: 1.45;
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
  padding: 7px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 700;
}

@media (max-width: 760px) {
  .page-head {
    display: grid;
  }

  .page-head :deep(.el-tag) {
    justify-self: start;
  }
}
</style>
