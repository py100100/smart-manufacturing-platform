# 智能制造服务平台 — 前端

基于 Vue3 + TypeScript + Vite + Element Plus 的企业级智能制造运营后台。

## 技术栈

| 层 | 技术 |
|----|------|
| 框架 | Vue3 + TypeScript |
| 构建 | Vite 5 |
| 路由 | Vue Router v4 |
| UI | Element Plus |
| 数据 | localStorage（演示/历史）+ Fetch API（后端联调） |

## 快速开始

推荐从项目根目录一键启动：

```bash
.\start-dev.bat
```

前端默认使用 `http://127.0.0.1:3000`；如果 3000 被占用，启动脚本会自动切换到 3001-3005 中的可用端口。浏览器打开启动窗口中打印的 `Frontend` 地址。

手动启动前端：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
npm run build                      # 生产构建 → dist/
```

如 3000 端口被占用，可手动换端口：

```bash
npm run dev -- --host 127.0.0.1 --port 3001 --strictPort
```

## 页面路由清单

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录页 | 本地演示认证，校验已注册账号 |
| `/register` | 注册页 | 本地演示注册，注册后可登录 |
| `/dashboard` | 运营总览驾驶台 | 默认首页，核心指标 + 风险概览 + 演示数据入口 |
| `/workspace` | 智能体工作台 | 自动路由/指定智能体 + 演示场景快捷按钮 |
| `/production` | 生产调度看板 | 排产分析、产能评估、交期风险 |
| `/quality` | 质量检测中心 | 缺陷分析、根因定位、良率监控 |
| `/maintenance` | 设备监控面板 | 振动分析、故障预测、维护计划 |
| `/supply-chain` | 供应链管理 | 库存分析、采购建议、缺料预警 |
| `/process` | 工艺优化分析 | 参数推荐、良率提升、效率优化 |
| `/closure` | 业务闭环中心 | 4 Tab（预警/工单/报告/行动项）+ 筛选 + 搜索 |
| `/history` | 历史记录 | localStorage 持久化，列表 + 详情 |
| `/profile` | 个人中心 | 账号信息展示 |

## 数据来源

| 数据类型 | 来源 | 持久化 |
|----------|------|--------|
| 智能体分析结果 | 后端 API (`/api/v1/agents/*`) | localStorage（历史记录） |
| 演示数据 | 前端 Mock (`demoDataService`) | localStorage（追加） |
| 登录态 | 前端 Mock (`authApi`) | localStorage |
| 仪表盘聚合 | 前端聚合 (`closureAggregateService`) | 实时计算 |

## 本地演示认证

当前使用前端本地认证，登录会校验已注册账号。
注册账号与登录态存储在 localStorage，刷新不丢失。

## 演示数据

在运营总览驾驶台点击"一键生成演示数据"，自动写入 6 条历史记录：
- 5 条单智能体场景（生产/质量/设备/供应链/工艺）
- 1 条三智能体全链路协同

演示数据与真实调用数据结构完全兼容，生成后 Dashboard 和 Closure Center 立即反映。

## 与后端接口关系

| 前端调用 | 后端接口 |
|----------|----------|
| `fetchAgentList()` | `GET /api/v1/agents/` |
| `executeAgent()` | `POST /api/v1/agents/execute` |
| `executeNamedAgent()` | `POST /api/v1/agents/{name}/execute` |

Vite 开发服务器自动代理 `/api` → `http://127.0.0.1:8000`。

## 当前限制

- 登录认证为 Mock 实现，未接真实用户系统
- 演示数据为前端生成，刷新后持久化但不同设备间不共享
- 业务页面指标第一版部分使用静态值（产能利用率 85%、在线设备 12），结合智能体结果动态更新
- 未接入图表库（ECharts/Recharts 预留）
- 不修改后端业务逻辑

## 项目结构

```
frontend/
├── src/
│   ├── api/           # API 封装（agentApi, authApi）
│   ├── types/         # TypeScript 类型定义
│   ├── services/      # 业务服务（auth, history, closureAggregate, demoData）
│   ├── components/    # 可复用组件
│   ├── views/         # 页面组件
│   ├── router.ts      # Vue Router 路由配置
│   ├── App.vue        # 应用入口组件
│   └── main.ts        # 入口
├── DEMO_SCRIPT.md     # 客户演示脚本
└── README.md          # 本文件
```
