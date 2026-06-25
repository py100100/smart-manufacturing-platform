<template>
  <AppLayout>
    <div class="workspace">
      <div class="panel page-head" :class="{ 'page-head--empty': !result }">
        <div class="head-copy">
          <h1 class="page-title">智能体工作台</h1>
          <div class="head-meta" aria-label="工作台能力">
            <span>自动路由</span>
            <span>指定智能体调用</span>
            <span>链式协同</span>
            <span>节点反馈可追溯</span>
          </div>
        </div>

        <div v-if="!result" class="head-empty-guide">
          <div class="head-empty-guide__intro">
            <h2>还没有分析结果</h2>
            <p>请按以下步骤操作：</p>
          </div>
          <div class="head-empty-steps">
            <div class="head-empty-step">
              <span>1</span>
              <div>
                <strong>输入业务问题</strong>
                <small>填写生产、质量、设备、供应链或工艺相关问题</small>
              </div>
            </div>
            <div class="head-empty-step">
              <span>2</span>
              <div>
                <strong>选择分析模式</strong>
                <small>使用自动路由，或手动指定某个业务智能体</small>
              </div>
            </div>
            <div class="head-empty-step">
              <span>3</span>
              <div>
                <strong>执行智能分析</strong>
                <small>系统会完成场景识别、证据检索和节点反馈</small>
              </div>
            </div>
            <div class="head-empty-step">
              <span>4</span>
              <div>
                <strong>查看结论与建议</strong>
                <small>阅读风险判断、处理步骤和完整分析详情</small>
              </div>
            </div>
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
                :rows="4"
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
          <div v-if="agents.length" class="agent-card-list">
            <button
              v-for="agent in agents"
              :key="agent.name"
              type="button"
              class="agent-card-item"
              :class="{ 'is-active': selectedAgent === agent.name }"
              @click="selectedAgent = selectedAgent === agent.name ? '' : agent.name"
            >
              <span class="agent-card-item__name">{{ agent.display_name }}</span>
              <span class="agent-card-item__hint">{{ agent.scenario_hint }}</span>
              <span class="agent-card-item__meta">
                {{ selectedAgent === agent.name ? '已指定调用' : '点击指定' }}
              </span>
            </button>
          </div>
          <el-empty v-else description="暂无可用智能体" :image-size="70" />
        </el-card>
      </div>

      <AgentResult v-if="result" :result="result" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import AppLayout from '../components/AppLayout.vue';
import AgentResult from '../components/AgentResult.vue';
import type { AgentExecutionResponse, AgentMeta } from '../types/agent';
import { executeAgent, executeNamedAgent, fetchAgentList } from '../api/agentApi';
import { saveHistory } from '../services/historyService';
import { getDemoScenarios } from '../services/demoDataService';

const route = useRoute();
const agents = ref<AgentMeta[]>([]);
const selectedAgent = ref('');
const requestText = ref('质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率');
const loading = ref(false);
const result = ref<AgentExecutionResponse | null>(null);
const scenarios = getDemoScenarios();

onMounted(async () => {
  // 若从首页问答入口带入问题，自动填充并切到自动路由模式
  const q = route.query.q;
  if (q && typeof q === 'string' && q.trim()) {
    requestText.value = q.trim();
    selectedAgent.value = '';
  }
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
  gap: 14px;
}

.page-head {
  display: grid;
  gap: 16px;
  padding: 18px 20px;
}

.page-head--empty {
  min-height: 196px;
  align-content: center;
}

.head-copy {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.scenario-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.head-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 2px;
  justify-content: flex-end;
}

.head-meta span {
  padding: 5px 9px;
  border: 1px solid #d9e0ea;
  border-radius: 4px;
  background: #f8fafc;
  color: #5b6678;
  font-size: 13px;
  font-weight: 650;
}

.head-empty-guide {
  width: min(1120px, 100%);
  margin: 0 auto;
}

.head-empty-guide__intro {
  text-align: center;
  margin-bottom: 12px;
}

.head-empty-guide__intro h2 {
  margin: 0 0 6px;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 700;
  color: #111827;
}

.head-empty-guide__intro p {
  margin: 0;
  color: #667085;
  font-size: 14px;
}

.head-empty-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.head-empty-step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
  min-height: 78px;
  padding: 12px;
  border: 1px solid #dbe5f2;
  border-radius: 5px;
  background: #fbfcfe;
}

.head-empty-step span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 4px;
  background: #eff6ff;
  color: #1f4e8c;
  font-size: 14px;
  font-weight: 800;
  flex-shrink: 0;
}

.head-empty-step strong {
  display: block;
  color: #172033;
  font-size: 14px;
  line-height: 1.5;
  font-weight: 700;
}

.head-empty-step small {
  display: block;
  margin-top: 3px;
  color: #667085;
  font-size: 12px;
  line-height: 1.55;
}

.two-col {
  align-items: start;
}

.agent-card-list {
  display: grid;
  gap: 10px;
  max-height: 300px;
  overflow: auto;
  padding-right: 4px;
}

.agent-card-item {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(122px, 0.42fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 14px;
  border: 1px solid #e1e7ef;
  border-radius: 5px;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
}

.agent-card-item:hover,
.agent-card-item.is-active {
  border-color: #9db2ce;
  background: #f8fafc;
}

.agent-card-item.is-active {
  border-left: 3px solid #1f4e8c;
}

.agent-card-item__name {
  color: #172033;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.agent-card-item__hint {
  color: #5b6678;
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: break-word;
}

.agent-card-item__meta {
  justify-self: end;
  padding: 5px 8px;
  border-radius: 4px;
  background: #eef6ff;
  color: #1f4e8c;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.scenario-buttons :deep(.el-button) {
  border-color: #d8e0ea;
  background: #f8fafc;
}

@media (max-width: 900px) {
  .head-copy {
    display: grid;
  }

  .head-meta {
    justify-content: flex-start;
  }

  .head-empty-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-card-item {
    grid-template-columns: 1fr;
  }

  .agent-card-item__meta {
    justify-self: start;
  }
}

@media (max-width: 640px) {
  .page-head {
    padding: 24px 20px 28px;
  }

  .head-empty-guide__intro h2 {
    font-size: 24px;
  }

  .head-empty-steps {
    grid-template-columns: 1fr;
  }
}
</style>
