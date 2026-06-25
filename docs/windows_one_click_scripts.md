# Windows One-Click Scripts

The project root keeps only the two user-facing launchers:

- `启动项目.bat`: start backend and frontend dev services, then open the frontend in the default browser.
- `停止项目.bat`: stop the services started by the launcher.

Implementation scripts live in `scripts/`:

- `scripts/start-dev.ps1`
- `scripts/stop-dev.ps1`

The launcher records process IDs and ports in `.runlogs/dev-services.json`.
`.runlogs/` is local runtime state and is ignored by Git.

Secrets are not stored in these scripts. Configure MySQL, Neo4j, and DeepSeek
through system environment variables or the ignored local `.env` file.

If the default ports are occupied, the launcher tries:

- Backend: `8000` to `8005`
- Frontend: `3000` to `3005`

By default, the launcher waits for the frontend and opens the actual frontend
URL in the default browser. For troubleshooting, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1 -NoBrowser
```
