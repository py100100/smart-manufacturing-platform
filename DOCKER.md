# Docker Deployment

## 1. Prepare Environment

Create a local Docker environment file from the example:

```powershell
Copy-Item .env.docker.example .env.docker
```

Edit `.env.docker` and replace `MYSQL_ROOT_PASSWORD` before using this outside a local demo.
If you want model calls inside Docker, set `DOCKER_DEEPSEEK_API_KEY` there as well.

## 2. Build And Start

```powershell
docker compose --env-file .env.docker up --build -d
```

After startup:

- Frontend: http://127.0.0.1:3001
- Backend API: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/api/v1/health
- API docs: http://127.0.0.1:8000/docs
- Neo4j Browser: http://127.0.0.1:7474

## 3. Useful Commands

```powershell
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend
docker compose --env-file .env.docker down
```

To remove the local MySQL data volume as well:

```powershell
docker compose --env-file .env.docker down -v
```

## Notes

- The backend reads service settings from environment variables only.
- The frontend is built as static files and served by Nginx.
- Browser requests to `/api/...` are proxied by Nginx to the backend container.
- MySQL data is stored in the `mysql_data` Docker volume.
- Neo4j data is stored in the `neo4j_data` Docker volume.
- MySQL is kept inside the Docker network by default, so it will not conflict with a local MySQL on port 3306.
- Neo4j is exposed on configurable local ports `NEO4J_HTTP_PORT` and `NEO4J_BOLT_PORT`.

## Optional Knowledge Graph Layer

Neo4j is enabled in `.env.docker.example` for the full-stack demo:

```text
NEO4J_ENABLED=true
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change_me_for_local_neo4j
```

Replace the demo password before real use. The backend health endpoint reports
`graph_ready` after a lightweight Neo4j `RETURN 1` probe.

## Optional MCP Tool Layer

MCP is disabled by default in `.env.docker.example`:

```text
MCP_ENABLED=false
```

To connect an external MCP-compatible tool service, set:

```text
MCP_ENABLED=true
MCP_SERVER_URL=http://your-mcp-server/rpc
MCP_TOOL_NAME=your.tool.name
MCP_AUTH_TOKEN=
MCP_TIMEOUT_SECONDS=5
```

The backend appends MCP tool evidence and node feedback to the normal agent
response. MCP failures are fail-soft and do not block the core agent workflow.
