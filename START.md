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
