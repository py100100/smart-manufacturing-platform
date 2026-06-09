<template>
  <div v-if="result" class="agent-result">
    <el-card shadow="never" class="panel">
      <template #header>
        <div class="panel-head-row">
          <div>
            <strong>{{ result.execution_mode === 'collaborative' ? '多智能体协同结果' : '单智能体分析结果' }}</strong>
            <div class="muted mono">Trace: {{ result.trace_id }}</div>
          </div>
          <el-tag :type="result.execution_mode === 'collaborative' ? 'warning' : 'success'">
            {{ result.execution_mode }}
          </el-tag>
        </div>
      </template>

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="执行智能体">{{ result.agent_name }}</el-descriptions-item>
        <el-descriptions-item label="识别场景">
          {{ result.detected_scenes?.join(' / ') || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="决策" :span="2">{{ result.decision }}</el-descriptions-item>
        <el-descriptions-item label="摘要" :span="2">{{ result.summary }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-grid result-sections">
        <div class="result-block">
          <h3>证据来源</h3>
          <ul class="result-list">
            <li v-for="item in result.evidence" :key="item">{{ item }}</li>
          </ul>
        </div>
        <div class="result-block">
          <h3>后续行动</h3>
          <ul class="result-list">
            <li v-for="item in result.next_actions" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>

      <el-tabs class="result-tabs">
        <el-tab-pane label="执行链路">
          <el-timeline>
            <el-timeline-item
              v-for="step in result.agent_chain"
              :key="step.agent_name + step.summary"
              :timestamp="step.display_name"
              placement="top"
            >
              <el-card shadow="never">
                <strong>{{ step.decision }}</strong>
                <p>{{ step.summary }}</p>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>
        <el-tab-pane label="节点反馈">
          <div v-for="node in result.node_feedback" :key="node.node_id" class="trace-line">
            <span class="trace-dot" />
            <div>
              <strong>{{ node.node_name }}</strong>
              <el-tag size="small" class="node-tag">{{ node.status }}</el-tag>
              <div class="muted">{{ node.detail }}</div>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="业务闭环">
          <el-row :gutter="12">
            <el-col :span="6"><el-statistic title="预警" :value="result.closure?.alerts?.length || 0" /></el-col>
            <el-col :span="6"><el-statistic title="工单" :value="result.closure?.work_orders?.length || 0" /></el-col>
            <el-col :span="6"><el-statistic title="报告" :value="result.closure?.reports?.length || 0" /></el-col>
            <el-col :span="6"><el-statistic title="行动项" :value="result.closure?.action_items?.length || 0" /></el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
  <el-empty v-else description="尚未执行分析" />
</template>

<script setup lang="ts">
import type { AgentExecutionResponse } from '../types/agent';

defineProps<{
  result: AgentExecutionResponse | null;
}>();
</script>

<style scoped>
.panel-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-sections {
  margin-top: 16px;
}

.result-block h3 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #172033;
}

.result-tabs {
  margin-top: 16px;
}

.node-tag {
  margin-left: 8px;
}
</style>
