# One-command startup

Run this from the project root:

```powershell
.\start-dev.bat
```

The launcher opens two service windows:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000` by default. If port 3000 is already occupied, the launcher automatically uses the next available port from 3001 to 3005 and prints the actual URL.

If this is the first run and `frontend/node_modules` does not exist, run once:

```powershell
cd frontend
npm install
```

After that, daily startup only needs `.\start-dev.bat`.

## Clean restart

When the browser still shows old frontend content, or ports are occupied by old dev servers, run these commands from the project root:

```powershell
Get-NetTCPConnection -LocalPort 8000,3000,3001,3002,3003,3004,3005 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }

Remove-Item -Recurse -Force frontend\dist, frontend\node_modules\.vite, .pytest_cache, .ruff_cache -ErrorAction SilentlyContinue

Get-ChildItem -Path . -Directory -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force

.\start-dev.bat
```

Then open the printed `Frontend` URL and press `Ctrl + F5` in the browser.

## Health check

Backend health endpoint:

```text
http://127.0.0.1:8000/api/v1/health
```

Expected fields:

- `database_ready`: `true` when local MySQL is running and `.env` matches the local account.
- `model_ready`: `true` when the model client or local fallback is available.
- `app_name` / `version`: application metadata.

For local MySQL, this project expects configuration through `.env`; do not hard-code database credentials in source code.
