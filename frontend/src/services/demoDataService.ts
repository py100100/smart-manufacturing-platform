import type { AgentExecutionResponse } from '../types/agent';
import { saveHistory } from './historyService';

// ══════════════════════════════════════════════════════════════════
// Mock 演示数据 — 与 AgentExecutionResponse 完全兼容
// ══════════════════════════════════════════════════════════════════

function now(): string {
  return new Date().toISOString();
}

function ago(minutes: number): string {
  return new Date(Date.now() - minutes * 60000).toISOString();
}

function makeSingleResponse(
  agentName: string,
  displayName: string,
  decision: string,
  summary: string,
  evidence: string[],
  nextActions: string[],
  alerts: any[],
  orders: any[],
  reports: any[],
  actionItems: any[],
): AgentExecutionResponse {
  return {
    trace_id: `demo-${agentName}-${Date.now()}`,
    request_text: `演示: ${summary.slice(0, 30)}`,
    execution_mode: 'single',
    detected_scenes: [agentName],
    agent_name: agentName,
    summary,
    decision,
    evidence,
    next_actions: nextActions,
    node_feedback: [
      { node_id: `${agentName}-intent`, node_name: '意图识别', status: 'completed', detail: `已识别为${displayName}场景` },
      { node_id: `${agentName}-analysis`, node_name: '规则分析', status: 'completed', detail: summary },
      { node_id: `${agentName}-decision`, node_name: '决策输出', status: 'completed', detail: decision },
      { node_id: `${agentName}-risk`, node_name: '风险评估', status: alerts.length ? 'warning' : 'success', detail: alerts.length ? `检测到${alerts.length}个风险` : '未检测到风险' },
    ],
    agent_chain: [{
      agent_name: agentName,
      display_name: displayName,
      status: 'completed',
      summary,
      decision,
      evidence: [...evidence, '[knowledge:项目方案] 基于Agentic RAG与多智能体协作智能制造服务平台'],
      next_actions: nextActions,
      node_feedback: [
        { node_id: `${agentName}-intent`, node_name: '意图识别', status: 'completed', detail: `已识别为${displayName}场景` },
        { node_id: `${agentName}-analysis`, node_name: '规则分析', status: 'completed', detail: summary },
        { node_id: `${agentName}-decision`, node_name: '决策输出', status: 'completed', detail: decision },
      ],
    }],
    closure: {
      alerts,
      work_orders: orders,
      reports,
      action_items: actionItems,
    },
  };
}

function makeCollaborativeResponse(): AgentExecutionResponse {
  const nowStr = now();
  return {
    trace_id: `demo-collab-${Date.now()}`,
    request_text: '演示: 质量缺陷率上升，设备振动传感器报警，需要优化工艺参数改善良品率',
    execution_mode: 'collaborative',
    detected_scenes: ['quality_inspection', 'predictive_maintenance', 'process_parameter_optimization'],
    agent_name: 'quality_inspection+predictive_maintenance+process_parameter_optimization',
    summary: '协同分析完成（质量检测 → 设备维护 → 工艺优化）：第1步-质量检测：缺陷率8%超标，集中在CNC工序；第2步-设备维护：主轴振动12mm/s，建议48h内维护；第3步-工艺优化：温度从860→840可提升良品率3%',
    decision: '协同决策-风险：quality_risk_detected | safety_risk_detected | optimization_recommended',
    evidence: [
      '[质量检测] 缺陷率 8%，超过阈值 5%',
      '[设备维护] 振动传感器读数 12mm/s，正常 < 10mm/s',
      '[工艺优化] 温度860时良品率92%，温度840时良品率95%',
      '[knowledge:项目方案] 基于Agentic RAG与多智能体协作智能制造服务平台',
    ],
    next_actions: [
      '复检批次 B001 全部产品',
      '48h内安排主轴维护',
      '调整热处理温度至840°C',
      '监控24h良品率变化',
      '通知质量主管和工艺工程师',
    ],
    node_feedback: [
      { node_id: 'quality_inspection/qi-intent', node_name: '意图识别', status: 'completed', detail: '已识别质量检测场景' },
      { node_id: 'quality_inspection/qi-analysis', node_name: '规则分析', status: 'completed', detail: '缺陷率超标' },
      { node_id: 'quality_inspection/qi-decision', node_name: '决策输出', status: 'completed', detail: 'quality_risk_detected' },
      { node_id: 'predictive_maintenance/pm-intent', node_name: '意图识别', status: 'completed', detail: '已识别设备维护场景' },
      { node_id: 'predictive_maintenance/pm-analysis', node_name: '规则分析', status: 'completed', detail: '振动超标需维护' },
      { node_id: 'predictive_maintenance/pm-decision', node_name: '决策输出', status: 'completed', detail: 'safety_risk_detected' },
      { node_id: 'process_parameter_optimization/po-intent', node_name: '意图识别', status: 'completed', detail: '已识别工艺优化场景' },
      { node_id: 'process_parameter_optimization/po-analysis', node_name: '规则分析', status: 'completed', detail: '温度偏高影响良率' },
      { node_id: 'process_parameter_optimization/po-decision', node_name: '决策输出', status: 'completed', detail: 'optimization_recommended' },
    ],
    agent_chain: [
      {
        agent_name: 'quality_inspection', display_name: '质量检测与缺陷分析', status: 'completed',
        summary: '缺陷率8%超标，集中在CNC工序', decision: 'quality_risk_detected',
        evidence: ['缺陷率 8%，超过阈值 5%', '[knowledge:项目方案] 基于Agentic RAG...'],
        next_actions: ['复检批次 B001 全部产品', '通知质量主管'],
        node_feedback: [
          { node_id: 'qi-intent', node_name: '意图识别', status: 'completed', detail: '已识别质量检测场景' },
          { node_id: 'qi-analysis', node_name: '规则分析', status: 'completed', detail: '缺陷率超标' },
          { node_id: 'qi-decision', node_name: '决策输出', status: 'completed', detail: 'quality_risk_detected' },
        ],
      },
      {
        agent_name: 'predictive_maintenance', display_name: '设备预测性维护', status: 'completed',
        summary: '主轴振动12mm/s，建议48h内维护', decision: 'safety_risk_detected',
        evidence: ['振动传感器读数 12mm/s，正常 < 10mm/s', '[knowledge:项目方案] 基于Agentic RAG...'],
        next_actions: ['48h内安排主轴维护', '更换轴承'],
        node_feedback: [
          { node_id: 'pm-intent', node_name: '意图识别', status: 'completed', detail: '已识别设备维护场景' },
          { node_id: 'pm-analysis', node_name: '规则分析', status: 'completed', detail: '振动超标需维护' },
          { node_id: 'pm-decision', node_name: '决策输出', status: 'completed', detail: 'safety_risk_detected' },
        ],
      },
      {
        agent_name: 'process_parameter_optimization', display_name: '工艺参数优化', status: 'completed',
        summary: '温度从860→840可提升良品率3%', decision: 'optimization_recommended',
        evidence: ['温度860时良品率92%', '温度840时良品率95%', '[knowledge:项目方案] 基于Agentic RAG...'],
        next_actions: ['调整热处理温度至840°C', '监控24h良品率变化'],
        node_feedback: [
          { node_id: 'po-intent', node_name: '意图识别', status: 'completed', detail: '已识别工艺优化场景' },
          { node_id: 'po-analysis', node_name: '规则分析', status: 'completed', detail: '温度偏高影响良率' },
          { node_id: 'po-decision', node_name: '决策输出', status: 'completed', detail: 'optimization_recommended' },
        ],
      },
    ],
    closure: {
      alerts: [
        { alert_id: 'ALERT-q1', source_agent: 'quality_inspection', severity: 'warning', alert_type: 'quality', title: '质量风险预警', message: '缺陷率8%超过阈值5%，集中在CNC工序', generated_at: nowStr, acknowledged: false },
        { alert_id: 'ALERT-pm1', source_agent: 'predictive_maintenance', severity: 'critical', alert_type: 'safety', title: '安全风险预警', message: '主轴振动12mm/s，正常<10mm/s，需立即维护', generated_at: nowStr, acknowledged: false },
        { alert_id: 'ALERT-po1', source_agent: 'process_parameter_optimization', severity: 'warning', alert_type: 'process', title: '工艺参数越界预警', message: '热处理温度偏高，影响良品率', generated_at: nowStr, acknowledged: false },
      ],
      work_orders: [
        { order_id: 'WO-pm1', source_agent: 'predictive_maintenance', order_type: 'maintenance', title: '设备维护工单 — 主轴振动超标', description: '主轴振动12mm/s需维护', priority: 'urgent', target_entity: 'CNC-001主轴', suggested_timing: '立即', status: 'pending', created_at: nowStr },
        { order_id: 'WO-sc1', source_agent: 'supply_chain_management', order_type: 'purchase', title: '采购工单 — 钢材库存不足', description: '钢材库存仅300kg，需采购700kg', priority: 'high', target_entity: 'MAT-001钢材', suggested_timing: '7日内', status: 'pending', created_at: nowStr },
        { order_id: 'WO-po1', source_agent: 'process_parameter_optimization', order_type: 'optimization', title: '工艺优化工单 — 热处理温度调整', description: '温度从860→840提升良品率3%', priority: 'medium', target_entity: 'temperature参数', suggested_timing: '本月内', status: 'pending', created_at: nowStr },
      ],
      reports: [
        { report_id: 'RPT-qi1', source_agents: ['quality_inspection'], title: '质量检测与缺陷分析 — 分析报告', summary: '缺陷率8%超标，集中在CNC工序', findings: ['缺陷率 8%，超过阈值 5%', '主要缺陷类型：尺寸偏差 60%，表面粗糙度 40%'], recommendations: ['复检批次 B001', '通知质量主管', '启动8D根因分析'], generated_at: nowStr },
        { report_id: 'RPT-pm1', source_agents: ['predictive_maintenance'], title: '设备预测性维护 — 分析报告', summary: '主轴振动超标需维护', findings: ['振动传感器读数 12mm/s', '正常范围 < 10mm/s', '轴承运行时间已达8000h'], recommendations: ['48h内安排主轴维护', '更换轴承'], generated_at: ago(2) },
        { report_id: 'RPT-col1', source_agents: ['quality_inspection', 'predictive_maintenance', 'process_parameter_optimization'], title: '多智能体协同分析 — 综合报告', summary: '全链路分析：质量→设备→工艺', findings: ['缺陷率超标', '设备振动异常', '工艺参数偏高'], recommendations: ['复检+维护+优化温度'], generated_at: nowStr },
      ],
      action_items: [
        { item_id: 'ACT-1', source_agent: 'quality_inspection', description: '复检批次 B001 全部产品', priority: 'high', status: 'pending', created_at: nowStr },
        { item_id: 'ACT-2', source_agent: 'predictive_maintenance', description: '48h内安排主轴维护', priority: 'urgent', status: 'pending', created_at: nowStr },
        { item_id: 'ACT-3', source_agent: 'process_parameter_optimization', description: '调整热处理温度至840°C', priority: 'medium', status: 'pending', created_at: nowStr },
        { item_id: 'ACT-4', source_agent: 'process_parameter_optimization', description: '监控24h良品率变化', priority: 'medium', status: 'pending', created_at: nowStr },
        { item_id: 'ACT-5', source_agent: 'quality_inspection', description: '通知质量主管和工艺工程师', priority: 'high', status: 'pending', created_at: nowStr },
      ],
    },
  };
}

// ══════════════════════════════════════════════════════════════════
// 公开接口
// ══════════════════════════════════════════════════════════════════

const DEMO_SCENARIOS = [
  {
    label: '生产计划延期风险',
    text: '本周排产计划中3个工单面临交期风险，CNC设备产能利用率已达92%，请分析瓶颈并提出排产优化建议',
  },
  {
    label: '质量缺陷与设备异常协同分析',
    text: '质量缺陷率上升至8%，同时CNC设备振动传感器读数异常达到12mm/s，需要综合分析质量根因和设备维护需求',
  },
  {
    label: '供应链缺料与采购建议',
    text: '生产计划需钢材2000kg，当前库存仅300kg，安全库存1000kg，供应商交付周期7天，请分析缺料风险并生成采购建议',
  },
  {
    label: '工艺参数优化提升良品率',
    text: '热处理工艺当前温度860°C导致良品率仅92%，历史数据显示840°C时良品率可达95%，请推荐最优工艺参数组合',
  },
  {
    label: '全链路综合风险分析',
    text: '质量缺陷率上升，设备振动传感器报警，供应链钢材库存不足，需要优化工艺参数来改善良品率，请进行全链路综合分析',
  },
];

export function getDemoScenarios() {
  return DEMO_SCENARIOS;
}

export function generateDemoHistory() {
  const scenarios = [
    {
      agentName: 'production_scheduling', displayName: '生产调度优化',
      decision: 'shortage_risk_detected', summary: '生产调度分析完成：3个工单存在交期风险，CNC设备产能利用率92%接近瓶颈，建议调整排产优先级',
      evidence: ['工单 WO-003 交期延迟 3 天', 'CNC 产能利用率 92%，接近瓶颈', '待排工单 12 个', '[knowledge:项目方案] 智能制造多智能体协作方案'],
      nextActions: ['调整工单 WO-003 优先级为高', '考虑外协加工分担产能', '通知生产主管确认交期'],
      alerts: [{ alert_id: 'ALERT-ps1', source_agent: 'production_scheduling', severity: 'warning', alert_type: 'process', title: '交期风险预警', message: '3个工单存在交期风险，CNC产能接近瓶颈', generated_at: ago(30), acknowledged: false }],
      orders: [{ order_id: 'WO-ps1', source_agent: 'production_scheduling', order_type: 'optimization', title: '排产调整工单', description: '调整工单优先级解决交期瓶颈', priority: 'high', target_entity: 'WO-003', suggested_timing: '本周内', status: 'pending', created_at: ago(30) }],
      reports: [{ report_id: 'RPT-ps1', source_agents: ['production_scheduling'], title: '生产调度优化 — 分析报告', summary: '发现3个交期风险工单，CNC产能瓶颈', findings: ['CNC产能利用率92%', '3个工单交期延迟'], recommendations: ['调整排产优先级', '考虑外协加工'], generated_at: ago(30) }],
      actions: [{ item_id: 'ACT-ps1', source_agent: 'production_scheduling', description: '调整工单 WO-003 优先级', priority: 'high', status: 'pending', created_at: ago(30) }],
    },
    {
      agentName: 'quality_inspection', displayName: '质量检测与缺陷分析',
      decision: 'quality_risk_detected', summary: '质量分析完成：缺陷率8%超标，主要缺陷类型为尺寸偏差(60%)和表面粗糙度(40%)，集中在CNC工序',
      evidence: ['缺陷率 8%，超过阈值 5%', '尺寸偏差占比 60%', '表面粗糙度占比 40%', '[knowledge:跨会话记忆] 质量检测与缺陷分析历史记录'],
      nextActions: ['复检批次 B001-B003', '启动8D根因分析', '通知质量主管', '加强CNC工序在线检测'],
      alerts: [{ alert_id: 'ALERT-qi2', source_agent: 'quality_inspection', severity: 'warning', alert_type: 'quality', title: '质量风险预警', message: '缺陷率8%超过阈值5%', generated_at: ago(25), acknowledged: false }],
      orders: [{ order_id: 'WO-qi1', source_agent: 'quality_inspection', order_type: 'inspection', title: '质检复检工单', description: '对缺陷批次进行全检', priority: 'high', target_entity: 'BATCH-B001', suggested_timing: '24小时内', status: 'pending', created_at: ago(25) }],
      reports: [{ report_id: 'RPT-qi2', source_agents: ['quality_inspection'], title: '质量检测与缺陷分析 — 分析报告', summary: '缺陷率8%超标', findings: ['缺陷率8%>5%', '尺寸偏差为主因'], recommendations: ['复检+8D分析'], generated_at: ago(25) }],
      actions: [{ item_id: 'ACT-qi1', source_agent: 'quality_inspection', description: '启动8D根因分析', priority: 'high', status: 'pending', created_at: ago(25) }],
    },
    {
      agentName: 'predictive_maintenance', displayName: '设备预测性维护',
      decision: 'safety_risk_detected', summary: '设备监控分析完成：CNC-001主轴振动12mm/s超过正常值10mm/s，轴承运行8000h接近寿命极限，建议48h内维护',
      evidence: ['振动传感器读数 12mm/s (正常 < 10mm/s)', '轴承运行 8000h (推荐更换 10000h)', '温度传感器 65°C (正常)', '[knowledge:项目方案] 基于Agentic RAG平台'],
      nextActions: ['48h内安排主轴维护', '更换轴承', '增加振动监测频率至每小时'],
      alerts: [{ alert_id: 'ALERT-pm2', source_agent: 'predictive_maintenance', severity: 'critical', alert_type: 'safety', title: '安全风险预警', message: '主轴振动12mm/s超限，需立即维护', generated_at: ago(20), acknowledged: false }],
      orders: [{ order_id: 'WO-pm2', source_agent: 'predictive_maintenance', order_type: 'maintenance', title: '设备维护工单 — CNC主轴', description: '主轴振动超标需维护更换轴承', priority: 'urgent', target_entity: 'CNC-001主轴', suggested_timing: '立即', status: 'pending', created_at: ago(20) }],
      reports: [{ report_id: 'RPT-pm2', source_agents: ['predictive_maintenance'], title: '设备预测性维护 — 分析报告', summary: '主轴振动超标需维护', findings: ['振动12mm/s>10mm/s', '轴承运行8000h'], recommendations: ['48h内维护', '更换轴承'], generated_at: ago(20) }],
      actions: [{ item_id: 'ACT-pm1', source_agent: 'predictive_maintenance', description: '48h内安排主轴维护', priority: 'urgent', status: 'pending', created_at: ago(20) }],
    },
    {
      agentName: 'supply_chain_management', displayName: '供应链协同管理',
      decision: 'critical_shortage', summary: '供应链分析完成：钢材严重缺料，需求2000kg，库存仅300kg，安全库存1000kg，预计缺口1700kg，建议紧急采购',
      evidence: ['钢材需求 2000kg', '当前库存 300kg', '安全库存 1000kg', '供应商 SUP-001 准时率 0.95', '[knowledge:跨会话记忆] 供应链历史记录'],
      nextActions: ['立即启动紧急采购流程', '采购钢材 1700kg', '联系供应商 SUP-001 确认交期', '调整后续采购计划'],
      alerts: [{ alert_id: 'ALERT-sc2', source_agent: 'supply_chain_management', severity: 'critical', alert_type: 'supply', title: '严重缺料预警', message: '钢材缺口1700kg，需紧急采购', generated_at: ago(15), acknowledged: false }],
      orders: [{ order_id: 'WO-sc2', source_agent: 'supply_chain_management', order_type: 'purchase', title: '紧急采购工单 — 钢材', description: '钢材缺口1700kg，紧急采购', priority: 'urgent', target_entity: 'MAT-001钢材', suggested_timing: '立即', status: 'pending', created_at: ago(15) }],
      reports: [{ report_id: 'RPT-sc1', source_agents: ['supply_chain_management'], title: '供应链协同管理 — 分析报告', summary: '钢材严重缺料需紧急采购', findings: ['缺口1700kg', 'SUP-001可靠'], recommendations: ['紧急采购+调拨'], generated_at: ago(15) }],
      actions: [{ item_id: 'ACT-sc1', source_agent: 'supply_chain_management', description: '紧急采购钢材 1700kg', priority: 'urgent', status: 'pending', created_at: ago(15) }],
    },
    {
      agentName: 'process_parameter_optimization', displayName: '工艺参数优化',
      decision: 'optimization_recommended', summary: '工艺优化分析完成：温度860°C时良品率92%，推荐降至840°C可提升至95%，预计缺陷率从8%降至5%',
      evidence: ['温度860°C → 良品率 92%', '温度840°C → 良品率 95%', '缺陷率预估从 8% → 5%', '[knowledge:项目方案] 智能制造方案'],
      nextActions: ['调整热处理温度至840°C', '监控24h良品率变化', '验证后更新工艺标准'],
      alerts: [{ alert_id: 'ALERT-po2', source_agent: 'process_parameter_optimization', severity: 'warning', alert_type: 'process', title: '工艺参数越界预警', message: '温度偏高影响良品率，推荐840°C', generated_at: ago(10), acknowledged: false }],
      orders: [{ order_id: 'WO-po2', source_agent: 'process_parameter_optimization', order_type: 'optimization', title: '工艺优化工单 — 热处理温度', description: '温度860→840提升良品率3%', priority: 'medium', target_entity: 'temperature参数', suggested_timing: '本月内', status: 'pending', created_at: ago(10) }],
      reports: [{ report_id: 'RPT-po1', source_agents: ['process_parameter_optimization'], title: '工艺参数优化 — 分析报告', summary: '温度调整可提升良品率3%', findings: ['860°C良品率92%', '840°C良品率95%'], recommendations: ['调温至840°C', '监控验证'], generated_at: ago(10) }],
      actions: [{ item_id: 'ACT-po1', source_agent: 'process_parameter_optimization', description: '调整热处理温度至840°C', priority: 'medium', status: 'pending', created_at: ago(10) }],
    },
  ];

  let count = 0;
  for (const s of scenarios) {
    const resp = makeSingleResponse(
      s.agentName, s.displayName, s.decision, s.summary,
      s.evidence, s.nextActions, s.alerts, s.orders, s.reports, s.actions,
    );
    saveHistory({
      mode: 'single',
      agentName: s.agentName,
      requestText: `演示: ${s.summary.slice(0, 50)}`,
      summary: s.summary,
      decision: s.decision,
      result: resp,
    });
    count++;
  }

  // 协同链路
  const collabResp = makeCollaborativeResponse();
  saveHistory({
    mode: 'collaborative',
    agentName: 'quality_inspection+predictive_maintenance+process_parameter_optimization',
    requestText: '演示: 质量缺陷率上升，设备振动传感器报警，需要优化工艺参数改善良品率',
    summary: collabResp.summary,
    decision: collabResp.decision,
    result: collabResp,
  });
  count++;

  return count;
}
