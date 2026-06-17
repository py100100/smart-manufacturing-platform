<template>
  <!-- ═══════════════════════════════════════════════════════════ -->
  <!-- 有结果时展示                                                -->
  <!-- ═══════════════════════════════════════════════════════════ -->
  <div v-if="result" class="agent-result">
    <!-- ── 智能分析结论（报告式顶部区域） ── -->
    <el-card shadow="hover" class="conclusion-card">
      <div class="conclusion-header">
        <span class="conclusion-title">智能分析结论</span>
        <span class="header-agent">{{ result.agent_name }}</span>
      </div>

      <!-- 报告正文：结构化块渲染 -->
      <div class="report-body">
        <template v-for="(block, bi) in summaryBlocks" :key="bi">
          <!-- 段落标题 -->
          <h3
            v-if="block.type === 'section'"
            class="block-section-title"
            v-html="formatInline(block.title)"
          />

          <!-- 步骤块 -->
          <div v-else-if="block.type === 'step'" class="block-step">
            <div class="block-step__header">
              <span class="block-step__num">{{ block.stepNum }}</span>
              <strong class="block-step__title" v-html="formatInline(block.title)" />
            </div>
            <div class="block-step__body">
              <template v-for="(line, li) in block.body" :key="li">
                <!-- 步骤内公式 -->
                <div v-if="line.kind === 'formula'" class="block-formula block-formula--inline">
                  <code class="block-formula__code">{{ formatFormula(line.text) }}</code>
                </div>
                <!-- 步骤内文本 -->
                <p v-else class="block-step__line" v-html="formatInline(line.text)" />
              </template>
            </div>
          </div>

          <!-- 公式块 -->
          <div v-else-if="block.type === 'formula'" class="block-formula">
            <span class="block-formula__label">公式</span>
            <code class="block-formula__code">{{ formatFormula(block.text) }}</code>
          </div>

          <!-- 普通段落 -->
          <p v-else class="block-paragraph" v-html="formatInline(block.text)" />
        </template>
      </div>

      <!-- 风险判断 -->
      <p class="report-decision">
        <span class="decision-label">风险判断：</span>
        <el-tag :type="decisionTagType" effect="light" size="large">
          {{ decisionLabel }}
        </el-tag>
      </p>

      <!-- 建议处理步骤（前 3 条） -->
      <div v-if="topActions.length" class="report-actions">
        <h4 class="report-actions__title">建议处理步骤</h4>
        <ol class="report-actions__list">
          <li v-for="(action, idx) in topActions" :key="idx">{{ action }}</li>
        </ol>
        <p
          v-if="result.next_actions && result.next_actions.length > 3"
          class="report-actions__more"
        >
          共 {{ result.next_actions.length }} 条，完整列表见下方分析详情
        </p>
      </div>
    </el-card>

    <!-- ── 分析路径图（命中方法型回答时显示） ── -->
    <el-card v-if="showMethodFlow" shadow="never" class="flow-card">
      <template #header><strong>分析路径图</strong></template>
      <div class="method-flow">
        <template v-for="(node, ni) in methodFlowNodes" :key="ni">
          <div class="flow-node">
            <span class="flow-node__step">{{ ni + 1 }}</span>
            <span class="flow-node__text">{{ node }}</span>
          </div>
          <div v-if="ni < methodFlowNodes.length - 1" class="flow-arrow">
            <span class="flow-arrow__line"></span>
            <span class="flow-arrow__head">&darr;</span>
          </div>
        </template>
      </div>
    </el-card>

    <!-- ── 分析详情（证据、全量步骤、链路、反馈、闭环） ── -->
    <el-card shadow="never" class="detail-panel">
      <template #header>
        <strong>分析详情</strong>
      </template>

      <!-- 分析依据 -->
      <div class="result-block">
        <h3>分析依据</h3>
        <ul v-if="result.evidence?.length" class="result-list">
          <li v-for="item in result.evidence" :key="item">{{ item }}</li>
        </ul>
        <el-empty v-else description="暂无分析依据" :image-size="40" />
      </div>

      <!-- 建议处理步骤（全量） -->
      <div class="result-block">
        <h3>建议处理步骤</h3>
        <ol v-if="result.next_actions?.length" class="result-list ordered">
          <li v-for="item in result.next_actions" :key="item">{{ item }}</li>
        </ol>
        <el-empty v-else description="暂无建议步骤" :image-size="40" />
      </div>

      <!-- Tab 区：执行链路 / 执行过程 / 业务闭环 -->
      <el-tabs class="result-tabs">
        <el-tab-pane label="执行链路">
          <el-timeline v-if="result.agent_chain?.length">
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
          <el-empty v-else description="暂无执行链路" :image-size="40" />
        </el-tab-pane>

        <el-tab-pane label="执行过程">
          <div
            v-for="node in result.node_feedback"
            :key="node.node_id"
            class="trace-line"
          >
            <span class="trace-dot" />
            <div>
              <strong>{{ node.node_name }}</strong>
              <el-tag size="small" class="node-tag">{{ node.status }}</el-tag>
              <div class="muted">{{ node.detail }}</div>
            </div>
          </div>
          <el-empty
            v-if="!result.node_feedback?.length"
            description="暂无执行过程"
            :image-size="40"
          />
        </el-tab-pane>

        <el-tab-pane label="业务闭环">
          <el-row :gutter="12">
            <el-col :span="6">
              <el-statistic
                title="预警"
                :value="result.closure?.alerts?.length || 0"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="工单"
                :value="result.closure?.work_orders?.length || 0"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="报告"
                :value="result.closure?.reports?.length || 0"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="行动项"
                :value="result.closure?.action_items?.length || 0"
              />
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>

      <!-- Trace ID（弱化展示，折叠区） -->
      <el-collapse class="trace-collapse">
        <el-collapse-item title="技术信息">
          <div class="trace-info">
            <span class="muted">Trace ID：</span>
            <span class="muted mono">{{ result.trace_id }}</span>
          </div>
          <div class="trace-info">
            <span class="muted">执行模式：</span>
            <span class="muted">
              {{ result.execution_mode === 'collaborative' ? '多智能体协同' : '单智能体' }}
            </span>
          </div>
          <div v-if="result.detected_scenes?.length" class="trace-info">
            <span class="muted">识别场景：</span>
            <span class="muted">{{ result.detected_scenes.join(' / ') }}</span>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>

  <!-- ═══════════════════════════════════════════════════════════ -->
  <!-- 空状态：轻量步骤引导                                         -->
  <!-- ═══════════════════════════════════════════════════════════ -->
  <el-card v-else shadow="never" class="empty-guide">
    <div class="empty-header">
      <h3>还没有分析结果</h3>
      <p class="empty-sub">请按以下步骤操作：</p>
    </div>
    <div class="empty-steps">
      <div class="empty-step">
        <span class="empty-step__num">1</span>
        <span class="empty-step__text">输入业务问题</span>
      </div>
      <div class="empty-step">
        <span class="empty-step__num">2</span>
        <span class="empty-step__text">选择自动路由或指定智能体</span>
      </div>
      <div class="empty-step">
        <span class="empty-step__num">3</span>
        <span class="empty-step__text">点击执行分析</span>
      </div>
      <div class="empty-step">
        <span class="empty-step__num">4</span>
        <span class="empty-step__text">查看智能分析结论和建议处理步骤</span>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentExecutionResponse } from '../types/agent'

const props = defineProps<{
  result: AgentExecutionResponse | null
}>()

// ═══════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════

type StepLine =
  | { kind: 'text'; text: string }
  | { kind: 'formula'; text: string }

type SummaryBlock =
  | { type: 'section'; title: string }
  | { type: 'step'; stepNum: number; title: string; body: StepLine[] }
  | { type: 'formula'; text: string }
  | { type: 'paragraph'; text: string }

// ═══════════════════════════════════════════════════════════════
// summary 解析：大段文本 → 结构化块
// ═══════════════════════════════════════════════════════════════

/** 识别形如【标题】的段落标题 */
const SECTION_RE = /^【(.+?)】\s*$/

/** 识别 Markdown 标题，如 ### 标题 / #### 3. 标题 */
const MARKDOWN_HEADING_RE = /^(#{1,6})\s+(.+)$/

/** 识别形如 "1. 数据基线建模" 或 "1. 数据基线建模" 的步骤标题 */
const STEP_HEADER_RE = /^(?:#{1,6}\s*)?(?:步骤\s*)?(\d{1,2})[.、)）:：]\s*(.+?)\s*[:：]?$/

/** 识别公式行（含 =、±、∑、希腊字母或下标模式） */
const FORMULA_RE = /[=±∑∏∫√∞αβγδλμσ]|_[{a-z0-9}]+|\\\[|\\\]|\\\(|\\\)|\\forall|\\exists|\\in|\\cap|\\cup|\\text|\\mathbf|\\hat|\\sum|\\sigma|\\mu/

/** 分析路径图触发关键词 */
const METHOD_FLOW_KEYWORDS = [
  'SPC', 'EWMA', 'CUSUM', 'Threshold_t', 'Upper_t', 'Lower_t',
  '自适应阈值', '预测性维护', '数据基线建模', 'SPC 动态控制限',
  '深度学习趋势预测', '阈值自适应修正', '报警决策',
  'AGV', 'AMR', 'ORCA', '机器人', '自主移动机器人', '密集仓储',
  '集中调度', '分布式避障', '混合控制', '路径规划', '时间窗',
  '安全速度', '重规划', '全局效率',
  '知识图谱', '实体抽取', '关系抽取', '信息抽取',
  '非结构化', '工艺文档', '维修记录',
  '三元组', '图谱推理',
]

/** 用户明确在问方法、流程、模型或技术路线时，才允许展示流程图 */
const METHOD_INTENT_KEYWORDS = [
  '如何', '怎么', '怎样', '方法', '方案', '步骤', '流程', '流程图',
  '路径图', '技术路线', '模型', '算法', '公式', '设计',
  '知识图谱', '实体抽取', '关系抽取', '图谱推理', '三元组',
  'AGV', 'AMR', 'ORCA', '机器人', '路径规划',
  'SPC', 'EWMA', 'CUSUM', 'RUL', '剩余寿命', '自适应阈值', '动态阈值',
]

function cleanMarkdownText(text: string): string {
  return text
    .trim()
    .replace(/^[-*]\s+/, '')
    .replace(/^#{1,6}\s+/, '')
    .replace(/^\*\*(.+?)\*\*\s*[:：]?$/, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\s*---+\s*$/, '')
    .trim()
}

function isDividerLine(line: string): boolean {
  return /^-{3,}$/.test(line.trim())
}

function isFormulaLine(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed) return false
  if (trimmed === '\\[' || trimmed === '\\]' || trimmed === '$$') return true
  return FORMULA_RE.test(trimmed)
}

function shouldAttachFormulaLine(line: string): boolean {
  const trimmed = line.trim()
  return (
    isFormulaLine(trimmed)
    || /^[（(]/.test(trimmed)
    || /其中|式中|上式中/i.test(trimmed)
  )
}

function parseSummary(text: string): SummaryBlock[] {
  if (!text) return []

  const rawLines = text.split('\n')
  const blocks: SummaryBlock[] = []
  let i = 0

  while (i < rawLines.length) {
    const line = rawLines[i]

    // 空行跳过
    if (line.trim() === '' || isDividerLine(line)) {
      i++
      continue
    }

    // 尝试匹配段落标题 【...】
    const sectionMatch = line.trim().match(SECTION_RE)
    if (sectionMatch) {
      blocks.push({ type: 'section', title: cleanMarkdownText(sectionMatch[1]) })
      i++
      continue
    }

    const headingMatch = line.trim().match(MARKDOWN_HEADING_RE)
    if (headingMatch) {
      const headingText = cleanMarkdownText(headingMatch[2])
      const headingStepMatch = headingText.match(STEP_HEADER_RE)
      if (!headingStepMatch) {
        blocks.push({ type: 'section', title: headingText })
        i++
        continue
      }
    }

    // 跳过 LaTeX 块的独立边界，真正公式内容在下一行收集
    if (line.trim() === '\\]' || line.trim() === '$$') {
      i++
      continue
    }

    // 尝试匹配步骤标题 "N. 标题"
    const stepMatch = line.trim().match(STEP_HEADER_RE)
    if (stepMatch) {
      const stepNum = parseInt(stepMatch[1], 10)
      const title = cleanMarkdownText(stepMatch[2])
      const body: StepLine[] = []
      i++
      // 收集步骤体，内部识别公式与文本
      while (i < rawLines.length) {
        const nextLine = rawLines[i]
        if (nextLine.trim() === '' || isDividerLine(nextLine)) {
          i++
          break
        }
        if (SECTION_RE.test(nextLine.trim()) || STEP_HEADER_RE.test(nextLine.trim())) {
          break
        }
        const heading = nextLine.trim().match(MARKDOWN_HEADING_RE)
        if (heading && !heading[2].match(STEP_HEADER_RE)) break
        // 公式行（步骤内部生效）
        if (isFormulaLine(nextLine)) {
          const fls: string[] = []
          const firstFormulaLine = nextLine.trim()
          if (firstFormulaLine !== '\\[' && firstFormulaLine !== '$$') {
            fls.push(firstFormulaLine)
          }
          i++
          while (i < rawLines.length) {
            const fl = rawLines[i].trim()
            if (fl === '' || isDividerLine(fl) || SECTION_RE.test(fl) || STEP_HEADER_RE.test(fl)) break
            if (fl === '\\]' || fl === '$$') {
              i++
              break
            }
            if (shouldAttachFormulaLine(fl)) {
              if (fl !== '\\[') fls.push(fl)
              i++
            } else {
              break
            }
          }
          if (fls.length) body.push({ kind: 'formula', text: fls.join('\n') })
          continue
        }
        body.push({ kind: 'text', text: cleanMarkdownText(nextLine) })
        i++
      }
      blocks.push({ type: 'step', stepNum, title, body })
      continue
    }

    // 识别公式行
    if (isFormulaLine(line)) {
      // 可能包含公式 + 说明文字，一起收集
      const formulaLines: string[] = []
      const firstLine = line.trim()
      if (firstLine !== '\\[' && firstLine !== '$$') {
        formulaLines.push(firstLine)
      }
      i++
      // 连续的公式/说明行
      while (i < rawLines.length) {
        const nl = rawLines[i].trim()
        if (nl === '' || isDividerLine(nl) || SECTION_RE.test(nl) || STEP_HEADER_RE.test(nl)) break
        if (nl === '\\]' || nl === '$$') {
          i++
          break
        }
        if (shouldAttachFormulaLine(nl)) {
          if (nl !== '\\[') formulaLines.push(nl)
          i++
        } else {
          break
        }
      }
      if (formulaLines.length) blocks.push({ type: 'formula', text: formulaLines.join('\n') })
      continue
    }

    // 默认：普通段落
    blocks.push({ type: 'paragraph', text: cleanMarkdownText(line) })
    i++
  }

  return blocks
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatInline(text: string): string {
  const escaped = escapeHtml(cleanMarkdownText(text))
  return escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 清除残留的反斜杠转义（LaTeX 残迹）
    .replace(/\\/g, '')
    // 清除残留的星号
    .replace(/(?<!\w)\*(?!\w)/g, '')
}

function formatFormula(text: string): string {
  return text
    .replace(/^[-*]\s+/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*/g, '')
    .replace(/\\\[/g, '')
    .replace(/\\\]/g, '')
    .replace(/\\\(/g, '')
    .replace(/\\\)/g, '')
    .replace(/\$\$/g, '')
    .replace(/\\\\/g, '\n')
    .replace(/\\forall/g, '∀')
    .replace(/\\exists/g, '∃')
    .replace(/\\in/g, '∈')
    .replace(/\\cap/g, '∩')
    .replace(/\\cup/g, '∪')
    .replace(/\\leq/g, '≤')
    .replace(/\\geq/g, '≥')
    .replace(/\\neq/g, '≠')
    .replace(/\\times/g, '×')
    .replace(/\\cdot/g, '·')
    .replace(/\\Delta/g, 'Δ')
    .replace(/\\alpha/g, 'α')
    .replace(/\\beta/g, 'β')
    .replace(/\\gamma/g, 'γ')
    .replace(/\\lambda/g, 'λ')
    .replace(/\\mu/g, 'μ')
    .replace(/\\sigma/g, 'σ')
    .replace(/\\quad/g, '  ')
    .replace(/\\mid/g, '|')
    .replace(/\\emptyset/g, '∅')
    .replace(/\\min/g, 'min')
    .replace(/\\max/g, 'max')
    .replace(/\\bigcap/g, '⋂')
    .replace(/\\langle/g, '〈')
    .replace(/\\rangle/g, '〉')
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1)/($2)')
    .replace(/\\operatorname\{([^{}]+)\}/g, '$1')
    .replace(/\\text\{([^{}]+)\}/g, '$1')
    .replace(/\\mathbf\{([^{}]+)\}/g, '$1')
    .replace(/\\mathcal\{([^{}]+)\}/g, '$1')
    .replace(/\\left|\\right/g, '')
    .replace(/\\lVert|\\rVert/g, '‖')
    .replace(/\\\|/g, '|')
    .replace(/\\[a-zA-Z]+/g, '')
    .replace(/\\/g, '')
    .replace(/\s+([,.;:，。；：])/g, '$1')
    .replace(/[{}]/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function containsAny(text: string, keywords: string[]): boolean {
  const upperText = text.toUpperCase()
  return keywords.some((kw) => upperText.includes(kw.toUpperCase()))
}

/** 判断是否展示方法流程图 */
function shouldShowMethodFlow(summary: string, requestText: string): boolean {
  if (!summary) return false

  // 关键修正：普通异常问题只展示业务答案，不因 summary 里的“根因/维护/图谱”等泛词误触发流程图。
  const hasMethodIntent = containsAny(requestText, METHOD_INTENT_KEYWORDS)
  if (!hasMethodIntent) return false

  const combinedText = `${requestText}\n${summary}`
  return containsAny(combinedText, METHOD_FLOW_KEYWORDS)
}

const PREDICTIVE_FLOW_STEPS = [
  '传感器数据采集',
  '数据基线建模',
  'SPC 动态控制限',
  '深度学习趋势预测',
  '阈值自适应修正',
  '报警决策',
]

const ROBOTICS_FLOW_STEPS = [
  '任务与地图输入',
  '集中调度分配',
  '路径与时间窗规划',
  '分布式实时避障',
  '状态反馈与重规划',
  '安全执行闭环',
]

const KNOWLEDGE_GRAPH_FLOW_STEPS = [
  '文档解析清洗',
  '实体类型定义',
  'NER实体抽取',
  '关系三元组抽取',
  '知识图谱构建',
  '根因路径推理',
]

function isRoboticsFlow(text: string): boolean {
  const upperText = text.toUpperCase()
  return [
    'AGV', 'AMR', 'ORCA', '机器人', '自主移动机器人', '密集仓储',
    '集中调度', '分布式避障', '混合控制', '路径规划', '时间窗',
  ].some((kw) => upperText.includes(kw.toUpperCase()))
}

function isKnowledgeGraphFlow(text: string): boolean {
  const upperText = text.toUpperCase()
  return [
    '知识图谱', '实体抽取', '关系抽取', '信息抽取',
    '非结构化', '工艺文档', '维修记录',
    '三元组', '图谱推理', 'NEO4J',
  ].some((kw) => upperText.includes(kw.toUpperCase()))
}

// ═══════════════════════════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════════════════════════

const summaryBlocks = computed(() => parseSummary(props.result?.summary ?? ''))

const showMethodFlow = computed(() => shouldShowMethodFlow(
  props.result?.summary ?? '',
  props.result?.request_text ?? '',
))

const methodFlowNodes = computed(() => {
  const summary = props.result?.summary ?? ''
  const requestText = props.result?.request_text ?? ''
  const text = `${requestText}\n${summary}`
  if (isKnowledgeGraphFlow(text)) return KNOWLEDGE_GRAPH_FLOW_STEPS
  if (isRoboticsFlow(text)) return ROBOTICS_FLOW_STEPS
  return PREDICTIVE_FLOW_STEPS
})

// ═══════════════════════════════════════════════════════════════
// 原有逻辑（不变）
// ═══════════════════════════════════════════════════════════════

const DECISION_CN_MAP: Record<string, string> = {
  quality_risk_detected: '检测到质量风险',
  schedule_risk_detected: '存在排产风险',
  maintenance_work_order_required: '建议生成维护工单',
  inventory_shortage_risk: '库存短缺风险',
  delivery_delay_risk: '交付延迟风险',
  equipment_fault_detected: '检测到设备异常',
  cost_overrun_warning: '成本超支预警',
  normal_operation: '运行正常',
  review_required: '需要人工复核',
}

function translateDecision(raw: string): string {
  if (!raw) return ''
  if (/[一-龥]/.test(raw)) return raw
  if (DECISION_CN_MAP[raw]) return DECISION_CN_MAP[raw]
  const normalized = raw.toLowerCase().replace(/[ _-]/g, '_')
  for (const [key, cn] of Object.entries(DECISION_CN_MAP)) {
    if (key.toLowerCase().replace(/[ _-]/g, '_') === normalized) return cn
  }
  return raw
}

const topActions = computed(() => {
  return props.result?.next_actions?.slice(0, 3) ?? []
})

const decisionTagType = computed(() => {
  const d = (props.result?.decision ?? '').toLowerCase()
  if (/紧急|严重|critical|severe|高风险|危险|异常|超支/.test(d)) return 'danger'
  if (/注意|警告|warning|中等|风险|延迟|短缺|预警/.test(d)) return 'warning'
  if (/正常|安全|通过|pass|ok|低风险/.test(d)) return 'success'
  return 'info'
})

const decisionLabel = computed(() => {
  const d = props.result?.decision ?? ''
  if (!d) return '暂无判断'
  return translateDecision(d)
})
</script>

<style scoped>
/* ═══════════════ 智能分析结论卡片 ═══════════════ */
.conclusion-card {
  margin-bottom: 16px;
  border-left: 4px solid var(--el-color-primary);
  background: #ffffff;
}

.conclusion-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.conclusion-title {
  font-size: 18px;
  font-weight: 700;
  color: #172033;
}

.header-agent {
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  padding: 2px 10px;
  border-radius: 4px;
}

/* ═══════════════ 报告正文：结构化块 ═══════════════ */
.report-body {
  margin-bottom: 20px;
}

/* 段落标题 */
.block-section-title {
  margin: 20px 0 12px;
  padding-left: 10px;
  border-left: 3px solid var(--el-color-primary);
  font-size: 16px;
  font-weight: 700;
  color: #172033;
  line-height: 1.4;
}

.block-section-title:first-child {
  margin-top: 0;
}

/* 步骤块 */
.block-step {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background: #fafbfc;
}

.block-step__header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--el-color-primary-light-9);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.block-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.block-step__title {
  font-size: 14px;
  font-weight: 600;
  color: #172033;
}

.block-step__body {
  padding: 12px 14px;
}

.block-step__line {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.7;
  color: #4a5568;
  overflow-wrap: break-word;
  word-break: break-word;
  white-space: pre-line;
}

.block-step__line:last-child {
  margin-bottom: 0;
}

/* 公式块 */
.block-formula {
  margin-bottom: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  overflow: hidden;
}

.block-formula__label {
  display: inline-block;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 0 0 6px 0;
}

.block-formula__code {
  display: block;
  padding: 12px 16px;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.8;
  color: #2d3748;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 步骤内部的公式块：更紧凑 */
.block-formula--inline {
  margin: 6px 0;
}

.block-formula--inline .block-formula__code {
  padding: 8px 14px;
  font-size: 12px;
  line-height: 1.6;
}

/* 普通段落 */
.block-paragraph {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.8;
  color: #4a5568;
  overflow-wrap: break-word;
  word-break: break-word;
  white-space: pre-line;
}

/* 风险判断 */
.report-decision {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 6px;
}

.decision-label {
  font-size: 14px;
  font-weight: 600;
  color: #4a5568;
  flex-shrink: 0;
}

/* ═══════════════ 分析路径图 ═══════════════ */
.flow-card {
  margin-bottom: 16px;
}

.method-flow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 10px 0;
}

.flow-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  min-width: 132px;
  min-height: 82px;
  box-shadow: 0 8px 18px rgb(15 23 42 / 0.05);
  transition: border-color 0.2s;
}

.flow-node:hover {
  border-color: var(--el-color-primary);
}

.flow-node__step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.flow-node__text {
  font-size: 13px;
  font-weight: 600;
  color: #4a5568;
  text-align: center;
  line-height: 1.4;
}

.flow-arrow {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 0 8px;
}

.flow-arrow__line {
  display: block;
  width: 22px;
  height: 1px;
  background: var(--el-border-color);
}

.flow-arrow__head {
  font-size: 12px;
  color: var(--el-color-primary);
  line-height: 1;
  transform: rotate(-90deg);
}

/* 响应式：移动端节点放宽宽度 */
@media (max-width: 640px) {
  .method-flow {
    flex-direction: column;
  }

  .flow-node {
    min-width: 220px;
    padding: 8px 14px;
  }

  .flow-arrow {
    flex-direction: column;
    padding: 2px 0;
  }

  .flow-arrow__line {
    width: 1px;
    height: 16px;
  }

  .flow-arrow__head {
    transform: none;
  }
}

/* 建议处理步骤（结论区前 3 条） */
.report-actions {
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.report-actions__title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #4a5568;
}

.report-actions__list {
  margin: 0;
  padding-left: 22px;
}

.report-actions__list li {
  margin-bottom: 6px;
  font-size: 14px;
  line-height: 1.6;
  color: #4a5568;
}

.report-actions__more {
  margin: 8px 0 0;
  font-size: 12px;
  color: #a0aec0;
}

/* ═══════════════ 分析详情面板 ═══════════════ */
.detail-panel {
  margin-bottom: 16px;
}

.result-block {
  margin-bottom: 20px;
}

.result-block h3 {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: #172033;
}

.result-list {
  margin: 0;
  padding-left: 20px;
}

.result-list li {
  margin-bottom: 6px;
  line-height: 1.6;
  color: #4a5568;
}

.result-list.ordered {
  padding-left: 22px;
}

.result-tabs {
  margin-top: 8px;
}

/* 执行过程 */
.node-tag {
  margin-left: 8px;
}

.trace-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
}

.trace-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--el-color-primary);
  margin-top: 5px;
  flex-shrink: 0;
}

/* Trace 折叠区 */
.trace-collapse {
  margin-top: 12px;
}

.trace-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #a0aec0;
  border-top: 1px solid var(--el-border-color-lighter);
}

.trace-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.trace-info {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  line-height: 1.6;
}

/* ═══════════════ 空状态引导 ═══════════════ */
.empty-guide {
  width: min(920px, 100%);
  min-height: 300px;
  margin: 0 auto;
}

.empty-guide :deep(.el-card__body) {
  padding: 38px 52px 42px;
}

.empty-header {
  text-align: center;
  margin-bottom: 34px;
}

.empty-header h3 {
  margin: 12px 0 6px;
  font-size: 22px;
  color: #172033;
}

.empty-sub {
  margin: 0;
  color: #718096;
  font-size: 15px;
}

.empty-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 22px;
  padding: 0;
}

.empty-step {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 54px;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.empty-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.empty-step__text {
  font-size: 15px;
  line-height: 1.5;
  color: #4a5568;
}

@media (max-width: 768px) {
  .empty-guide :deep(.el-card__body) {
    padding: 28px 22px 30px;
  }

  .empty-steps {
    grid-template-columns: 1fr;
  }
}

/* ═══════════════ 通用 ═══════════════ */
.muted {
  font-size: 12px;
  color: #a0aec0;
}

.mono {
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
</style>
