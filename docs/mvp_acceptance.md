# MVP Acceptance Checklist

## Scope

The MVP is a stable full-stack demo for the intelligent manufacturing platform.
It proves the existing multi-agent workflow, RAG evidence, database persistence,
knowledge graph connectivity, and business closure output without adding new
workflow frameworks.

## Demo Flow

1. Open the dashboard and confirm system health for MySQL, DeepSeek, and Neo4j.
2. Pick one of the five MVP demo scenarios.
3. Run the request in the agent workspace.
4. Verify `summary`, `decision`, `evidence`, `next_actions`, and `node_feedback`.
5. Open the closure center and review alerts, work orders, reports, and action items.
6. Open history and confirm the execution can be traced by request and result.

## Required Backend Signals

- `GET /api/v1/health` returns `database_ready`, `model_ready`, and `graph_ready`.
- `GET /api/v1/agents/` returns the five registered business agents.
- `POST /api/v1/agents/execute` supports automatic routing and collaborative mode.
- `POST /api/v1/agents/{agent_name}/execute` supports direct agent execution.
- `GET /api/v1/demo/mvp` returns health, agents, demo scenarios, and acceptance flow.

## Required Frontend Signals

- Dashboard displays the MVP health strip.
- Dashboard scenario buttons open the workspace with the selected prompt.
- Workspace can execute both automatic routing and named-agent requests.
- Agent results show conclusion, evidence, actions, node feedback, chain, and closure.
- Demo history can be generated for offline walkthroughs.

## Environment

- MySQL 8.4 on port `3306`.
- Neo4j on Bolt port `7687`.
- DeepSeek API key read from environment only.
- No real secrets are committed to source files.
