import type { AgentExecutionRequest, AgentExecutionResponse, AgentMeta } from '../types/agent';

const BASE = '/api/v1/agents';

export async function fetchAgentList(): Promise<AgentMeta[]> {
  const res = await fetch(BASE + '/');
  if (!res.ok) throw new Error(`获取智能体列表失败: ${res.status}`);
  return res.json();
}

export async function executeAgent(
  body: AgentExecutionRequest
): Promise<AgentExecutionResponse> {
  const res = await fetch(BASE + '/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`执行失败: ${res.status} ${err}`);
  }
  return res.json();
}

export async function executeNamedAgent(
  agentName: string,
  body: AgentExecutionRequest
): Promise<AgentExecutionResponse> {
  const res = await fetch(`${BASE}/${agentName}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`执行失败: ${res.status} ${err}`);
  }
  return res.json();
}
