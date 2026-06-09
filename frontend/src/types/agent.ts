// ══════════════════════════════════════════════════════════════════
// 智能体相关类型
// ══════════════════════════════════════════════════════════════════

export interface AgentMeta {
  name: string;
  display_name: string;
  scenario_hint: string;
  input_schema: string;
  output_schema: string;
}

export interface NodeFeedback {
  node_id: string;
  node_name: string;
  status: string;
  detail: string;
  started_at?: string;
  completed_at?: string;
}

export interface AgentStep {
  agent_name: string;
  display_name: string;
  status: string;
  summary: string;
  decision: string;
  evidence: string[];
  next_actions: string[];
  node_feedback: NodeFeedback[];
}

export interface Alert {
  alert_id: string;
  source_agent: string;
  severity: 'critical' | 'warning' | 'info';
  alert_type: string;
  title: string;
  message: string;
  generated_at: string;
  acknowledged: boolean;
}

export interface WorkOrder {
  order_id: string;
  source_agent: string;
  order_type: 'maintenance' | 'purchase' | 'optimization' | 'inspection';
  title: string;
  description: string;
  priority: 'urgent' | 'high' | 'medium' | 'low';
  target_entity: string;
  suggested_timing: string;
  status: string;
  created_at: string;
}

export interface Report {
  report_id: string;
  source_agents: string[];
  title: string;
  summary: string;
  findings: string[];
  recommendations: string[];
  generated_at: string;
}

export interface ActionItem {
  item_id: string;
  source_agent: string;
  description: string;
  priority: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  created_at: string;
  due_date?: string;
}

export interface Closure {
  alerts: Alert[];
  work_orders: WorkOrder[];
  reports: Report[];
  action_items: ActionItem[];
}

export interface AgentExecutionResponse {
  trace_id: string;
  request_text: string;
  execution_mode: 'single' | 'collaborative';
  detected_scenes: string[];
  agent_name: string;
  summary: string;
  decision: string;
  evidence: string[];
  next_actions: string[];
  agent_chain: AgentStep[];
  node_feedback: NodeFeedback[];
  closure: Closure;
}

export interface AgentExecutionRequest {
  request_text: string;
  agent_name?: string;
  require_llm?: boolean;
}

export interface HistoryEntry {
  id: string;
  timestamp: string;
  mode: 'single' | 'collaborative';
  agentName: string;
  requestText: string;
  summary: string;
  decision: string;
  result: AgentExecutionResponse;
}
