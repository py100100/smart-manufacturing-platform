import type { AgentExecutionResponse, HistoryEntry } from '../types/agent';

const HISTORY_KEY = 'sm_history';

export function saveHistory(entry: Omit<HistoryEntry, 'id' | 'timestamp'>): HistoryEntry {
  const record: HistoryEntry = {
    ...entry,
    id: `hist-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
  };
  const list = getHistory();
  list.unshift(record);
  // 保留最近 50 条
  if (list.length > 50) list.length = 50;
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
  return record;
}

export function getHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function getHistoryById(id: string): HistoryEntry | undefined {
  return getHistory().find((h) => h.id === id);
}

export function clearHistory(): void {
  localStorage.removeItem(HISTORY_KEY);
}
