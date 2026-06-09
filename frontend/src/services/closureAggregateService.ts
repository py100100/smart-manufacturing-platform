import { getHistory } from './historyService';
import type { Alert, WorkOrder, Report, ActionItem } from '../types/agent';

// ══════════════════════════════════════════════════════════════════
// 聚合类型
// ══════════════════════════════════════════════════════════════════

export interface DashboardSummary {
  totalCalls: number;
  collaborativeCalls: number;
  todayCalls: number;
  totalAlerts: number;
  criticalAlerts: number;
  warningAlerts: number;
  infoAlerts: number;
  pendingWorkOrders: number;
  pendingActions: number;
  recentReportsCount: number;
  agentUsage: { name: string; displayName: string; count: number }[];
  recentAlerts: Alert[];
  recentWorkOrders: WorkOrder[];
  recentReports: Report[];
  recentActions: ActionItem[];
  recentChains: { id: string; agents: string[]; timestamp: string }[];
}

// ══════════════════════════════════════════════════════════════════
// 聚合函数
// ══════════════════════════════════════════════════════════════════

const AGENT_DISPLAY: Record<string, string> = {
  production_scheduling: '生产调度',
  quality_inspection: '质量检测',
  predictive_maintenance: '设备维护',
  supply_chain_management: '供应链',
  process_parameter_optimization: '工艺优化',
};

export function computeDashboardSummary(): DashboardSummary {
  const history = getHistory();
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();

  // 今日调用
  const todayEntries = history.filter((h) => h.timestamp >= todayStart);

  // 聚合所有 closure 对象
  const allAlerts: Alert[] = [];
  const allWorkOrders: WorkOrder[] = [];
  const allReports: Report[] = [];
  const allActions: ActionItem[] = [];
  const allChains: { id: string; agents: string[]; timestamp: string }[] = [];
  const agentCount: Record<string, number> = {};

  for (const entry of history) {
    const c = entry.result?.closure;
    if (!c) continue;

    allAlerts.push(...(c.alerts ?? []));
    allWorkOrders.push(...(c.work_orders ?? []));
    allReports.push(...(c.reports ?? []));
    allActions.push(...(c.action_items ?? []));

    // 协同链：按每个 agent 分摊计数
    const chain = entry.result?.agent_chain;
    if (chain && chain.length > 1) {
      allChains.push({
        id: entry.id,
        agents: chain.map((s) => s.agent_name),
        timestamp: entry.timestamp,
      });
      for (const step of chain) {
        const name = step.agent_name;
        if (name) agentCount[name] = (agentCount[name] || 0) + 1;
      }
    } else {
      // 单智能体
      const agentName = entry.agentName ?? entry.result?.agent_name ?? '';
      if (agentName) {
        agentCount[agentName] = (agentCount[agentName] || 0) + 1;
      }
    }
  }

  const criticalAlerts = allAlerts.filter((a) => a.severity === 'critical');
  const warningAlerts = allAlerts.filter((a) => a.severity === 'warning');
  const infoAlerts = allAlerts.filter((a) => a.severity === 'info');

  const agentUsage = Object.entries(agentCount)
    .map(([name, count]) => ({
      name,
      displayName: AGENT_DISPLAY[name] ?? name,
      count,
    }))
    .sort((a, b) => b.count - a.count);

  return {
    totalCalls: history.length,
    collaborativeCalls: history.filter((h) => h.mode === 'collaborative').length,
    todayCalls: todayEntries.length,
    totalAlerts: allAlerts.length,
    criticalAlerts: criticalAlerts.length,
    warningAlerts: warningAlerts.length,
    infoAlerts: infoAlerts.length,
    pendingWorkOrders: allWorkOrders.filter((w) => w.status === 'pending').length,
    pendingActions: allActions.filter((a) => a.status === 'pending').length,
    recentReportsCount: allReports.length,
    agentUsage,
    recentAlerts: allAlerts.slice(-5).reverse(),
    recentWorkOrders: allWorkOrders.slice(-5).reverse(),
    recentReports: allReports.slice(-5).reverse(),
    recentActions: allActions.slice(-5).reverse(),
    recentChains: allChains.slice(-5).reverse(),
  };
}

export function getAllAlerts(): Alert[] {
  const history = getHistory();
  return history.flatMap((h) => h.result?.closure?.alerts ?? []);
}

export function getAllWorkOrders(): WorkOrder[] {
  const history = getHistory();
  return history.flatMap((h) => h.result?.closure?.work_orders ?? []);
}

export function getAllReports(): Report[] {
  const history = getHistory();
  return history.flatMap((h) => h.result?.closure?.reports ?? []);
}

export function getAllActions(): ActionItem[] {
  const history = getHistory();
  return history.flatMap((h) => h.result?.closure?.action_items ?? []);
}
