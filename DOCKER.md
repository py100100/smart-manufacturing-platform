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
- MySQL is kept inside the Docker network by default, so it will not conflict with a local MySQL on port 3306.

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
