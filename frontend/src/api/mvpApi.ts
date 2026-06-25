import type { AgentMeta } from '../types/agent';

export interface MvpHealth {
  database_ready: boolean;
  model_ready: boolean;
  graph_ready: boolean;
}

export interface MvpScenario {
  id: string;
  title: string;
  agent_name: string | null;
  expected_mode: 'single' | 'collaborative';
  request_text: string;
}

export interface MvpManifest {
  name: string;
  status: 'ready' | 'degraded';
  health: MvpHealth;
  agents: Pick<AgentMeta, 'name' | 'display_name' | 'scenario_hint'>[];
  scenarios: MvpScenario[];
  acceptance_flow: string[];
}

export async function fetchMvpManifest(): Promise<MvpManifest> {
  const res = await fetch('/api/v1/demo/mvp');
  if (!res.ok) throw new Error(`MVP manifest failed: ${res.status}`);
  return res.json();
}
