# MCP Integration Plan

## Positioning

MCP is an optional enterprise tool access layer. It is not required for the core
agent workflow, database startup, local RAG fallback, or Docker demo.

## Runtime Flow

1. `AgentOrchestrator.execute()` asks `MCPGateway` for optional context.
2. When `MCP_ENABLED=false`, the gateway returns no nodes and the existing
   agent path is unchanged.
3. When enabled, the gateway calls the configured MCP endpoint through JSON-RPC.
4. Tool results are added as top-level `evidence`.
5. Tool success, skipped state, or failure is appended to `node_feedback`.
6. External MCP errors are fail-soft and never block the agent response.

## Environment Variables

```text
MCP_ENABLED=false
MCP_SERVER_URL=
MCP_TOOL_NAME=
MCP_AUTH_TOKEN=
MCP_TIMEOUT_SECONDS=5
```

`MCP_TOOL_NAME` is optional. If empty, the gateway performs `tools/list` so the
interface can show tool discovery feedback. If set, the gateway calls
`tools/call` with:

```json
{
  "query": "user request text",
  "context": {}
}
```

## Guardrails

- No MCP endpoint or token is hard-coded in source.
- Full external tool payloads are not logged.
- Evidence snippets are capped before being returned.
- MCP nodes use the same `node_feedback` contract as agents.
