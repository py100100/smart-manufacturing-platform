# 一键启动说明

在项目根目录执行：

```powershell
.\start-dev.bat
```

启动脚本会自动打开两个服务窗口：

- 后端服务：`http://127.0.0.1:8000`
- 前端服务：默认 `http://127.0.0.1:3000`。如果 3000 端口已被占用，脚本会自动尝试 3001 到 3005 中的可用端口，并在窗口中打印实际访问地址。

如果是第一次运行，并且 `frontend/node_modules` 不存在，需要先安装一次前端依赖：

```powershell
cd frontend
npm install
```

之后日常启动只需要执行：

```powershell
.\start-dev.bat
```

## 清除缓存并重新启动

当浏览器仍然显示旧页面，或者端口被之前的开发服务占用时，可以在项目根目录执行下面命令：

```powershell
Get-NetTCPConnection -LocalPort 8000,3000,3001,3002,3003,3004,3005 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }

Remove-Item -Recurse -Force frontend\dist, frontend\node_modules\.vite, .pytest_cache, .ruff_cache -ErrorAction SilentlyContinue

Get-ChildItem -Path . -Directory -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force

.\start-dev.bat
```

然后打开启动窗口中打印的 `Frontend` 地址，并在浏览器中按 `Ctrl + F5` 强制刷新。

## 健康检查

后端健康检查地址：

```text
http://127.0.0.1:8000/api/v1/health
```

正常情况下会返回以下字段：

- `database_ready`：本地 MySQL 已启动，并且 `.env` 中的数据库账号配置正确时为 `true`。
- `model_ready`：模型客户端可用，或本地兜底能力可用时为 `true`。
- `app_name` / `version`：应用名称和版本信息。

本地 MySQL 配置需要写在 `.env` 文件中，不要把数据库账号、密码硬编码到源码里。
