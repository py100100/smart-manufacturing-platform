# 智能制造服务平台

基于 Agentic RAG 与多智能体协作的企业级智能制造服务平台。

## 项目启动

日常前后端联调推荐使用一键启动：

```powershell
.\start-dev.bat
```

脚本会分别打开后端与前端服务窗口。前端默认使用 `http://127.0.0.1:3000`；如果 3000 端口已被占用，脚本会自动切换到 3001-3005 中的可用端口。浏览器访问启动窗口中打印的 `Frontend` 地址即可。

手动启动与验收命令：

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动后端
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 启动前端
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000

# 如果 3000 被占用，可手动换端口
npm run dev -- --host 127.0.0.1 --port 3001 --strictPort

# 运行测试
python hooks/check_claude.py
python -m pytest tests/ -q
```

## 目录说明

| 路径 | 说明 |
|------|------|
| `app/` | 后端 API、智能体、服务、Schema、数据库模块 |
| `frontend/` | Web 前端工程 |
| `tests/` | 后端自动化测试 |
| `hooks/` | 提交前护栏扫描脚本 |
| `docs/reports/` | 项目日报、客户汇报材料 |
| `logs/` | 本地运行日志 |
| `archive/` | 临时文件归档 |

## 五个业务智能体

| 智能体 | 名称 | 职责 |
|--------|------|------|
| 生产调度优化 | `production_scheduling` | 排产、工单、产能、交期、瓶颈分析 |
| 质量检测与缺陷分析 | `quality_inspection` | 质量、缺陷、不良率、根因分析 |
| 设备预测性维护 | `predictive_maintenance` | 设备振动、温度、电流、传感器、故障预警 |
| 供应链协同管理 | `supply_chain_management` | 库存、采购、供应商、缺料、积压 |
| 工艺参数优化 | `process_parameter_optimization` | 温度、压力、速度、良品率、参数推荐 |

## Agentic RAG 实现

当前 RAG 层位于 `app/services/knowledge_service.py`：

- 优先使用 `LangChain + Chroma` 构建本地内存向量检索。
- 使用离线 `LocalHashEmbeddings`，无需外部模型服务或 API Key 即可演示。
- 当 LangChain/Chroma 依赖不可用或初始化失败时，自动回退到 TF-IDF 检索。
- 对外接口保持不变：智能体仍通过 `KnowledgeService.retrieve()` 获取带来源的证据。

智能体编排由自研 `AgentOrchestrator` 负责：自动路由、指定智能体调用、多智能体协同链路、节点反馈聚合和业务答案质量兜底。

## 业务答案合成与质量门

为避免智能体只返回“已接收请求”或“请提供结构化数据”等流程性话术，项目增加了统一的业务答案增强层：

- `app/services/business_answer_service.py`：负责识别业务解释型问题，并按生产、质量、设备、供应链、工艺等领域生成结构化专家答案。
- `app/services/orchestrator.py`：在单智能体、指定智能体和协同执行后，对顶层 `summary` 进行质量检查。
- 当 `summary` 过短或包含空洞话术时，Orchestrator 会调用 `BusinessAnswerService` 生成兜底答案，并追加 `answer-synthesis` / `答案综合` 节点。
- `agent_chain` 中保留各智能体原始执行摘要，方便追溯；顶层 `summary` 用于前端展示高质量业务结论。
- `require_llm=false` 时走本地专家模板，不调用外部模型；`require_llm=true` 时优先尝试模型生成，失败后回退本地模板。

## API 接口

### `GET /api/v1/agents/`

列出全部已注册智能体及元数据。

### `POST /api/v1/agents/execute`

统一执行入口 — 自动检测业务场景，路由到最匹配的智能体。

**单智能体调用示例：**

```bash
curl -X POST http://localhost:8000/api/v1/agents/execute \
  -H "Content-Type: application/json" \
  -d '{"request_text": "分析最近批次的质量缺陷和不良率原因", "require_llm": false}'
```

### `POST /api/v1/agents/{agent_name}/execute`

按名称直接调用指定智能体。

**示例：**

```bash
# 调用供应链智能体
curl -X POST http://localhost:8000/api/v1/agents/supply_chain_management/execute \
  -H "Content-Type: application/json" \
  -d '{"request_text": "分析库存缺料风险", "require_llm": false}'

# 调用工艺优化智能体
curl -X POST http://localhost:8000/api/v1/agents/process_parameter_optimization/execute \
  -H "Content-Type: application/json" \
  -d '{"request_text": "优化热处理温度和压力参数", "require_llm": false}'
```

**多智能体协同调用示例：**

```bash
curl -X POST http://localhost:8000/api/v1/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "request_text": "质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率",
    "require_llm": false
  }'
```

## 返回字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | string | 请求追踪 ID |
| `execution_mode` | string | `"single"` 单智能体 / `"collaborative"` 多智能体协同 |
| `detected_scenes` | list[string] | 识别到的业务场景列表 |
| `agent_name` | string | 执行的智能体名称（协同模式为 `+` 连接） |
| `summary` | string | 顶层分析摘要；经过业务答案质量门校验，必要时由答案综合层兜底生成 |
| `decision` | string | 智能体决策 |
| `evidence` | list[string] | 支撑证据（含 `[knowledge:来源]` 知识库标记） |
| `next_actions` | list[string] | 建议后续行动 |
| `node_feedback` | list[object] | 聚合所有智能体的节点式反馈；业务答案增强时会包含 `answer-synthesis` 节点 |
| `agent_chain` | list[object] | 执行链路，每步含 `agent_name`、`display_name`、`summary`、`decision`、`evidence`、`node_feedback` |
| `closure` | object | 业务闭环对象 |
| `closure.alerts` | list[object] | 预警列表（`alert_id`、`severity`、`alert_type`、`title`） |
| `closure.work_orders` | list[object] | 工单列表（`order_id`、`order_type`、`priority`、`target_entity`） |
| `closure.reports` | list[object] | 分析报告（`report_id`、`findings`、`recommendations`） |
| `closure.action_items` | list[object] | 后续行动项（`item_id`、`description`、`status`） |

## 验收测试

```bash
# Hook 校验
python hooks/check_claude.py

# 全部测试
python -m pytest tests/ -q

# 按模块测试
python -m pytest tests/test_guardrails.py tests/test_orchestrator.py -q
python -m pytest tests/test_production_scheduling_agent.py -q
python -m pytest tests/test_quality_inspection_agent.py -q
python -m pytest tests/test_predictive_maintenance_agent.py -q
python -m pytest tests/test_supply_chain_management_agent.py -q
python -m pytest tests/test_process_parameter_optimization_agent.py -q
python -m pytest tests/test_business_closure.py -q
python -m pytest tests/test_knowledge_rag.py -q
python -m pytest tests/test_integration.py -q
python -m pytest tests/test_business_answer_service.py -q
python -m pytest tests/test_orchestrator.py::TestSingleAgentEndpointSummaryQuality -q
```

最近一次拆分验收结果：Hook 通过；`test_orchestrator.py` 285 passed；五个智能体模块 269 passed；`business_answer_service` 19 passed；闭环、护栏、RAG、集成测试合计 109 passed；前端 `npm run build` 通过。全量一次性运行可能因本地环境超时，可按上面的模块命令拆分验收。

## 项目结构

```
smart-manufacturing-platform/
├── app/                                      # 后端 FastAPI 主工程
│   ├── main.py                              # FastAPI 应用入口
│   ├── api/
│   │   ├── router.py                        # API 路由汇总
│   │   └── v1/endpoints/
│   │       ├── agents.py                    # 智能体统一执行、指定智能体调用接口
│   │       ├── governance.py                # 治理/闭环相关接口
│   │       └── health.py                    # 健康检查接口
│   ├── agents/                              # 五个业务智能体及注册中心
│   │   ├── base.py                          # 智能体基础类与统一输出约束
│   │   ├── registry.py                      # 智能体注册与查询
│   │   ├── production_scheduling_agent.py   # 生产调度优化智能体
│   │   ├── quality_inspection_agent.py      # 质量检测与缺陷分析智能体
│   │   ├── predictive_maintenance_agent.py  # 设备预测性维护智能体
│   │   ├── supply_chain_management_agent.py # 供应链协同管理智能体
│   │   └── process_parameter_optimization_agent.py # 工艺参数优化智能体
│   ├── services/                            # 业务服务与智能编排层
│   │   ├── orchestrator.py                  # 自动路由、多智能体协同、答案质量门
│   │   ├── business_answer_service.py       # 业务答案增强与兜底专家模板
│   │   ├── knowledge_service.py             # LangChain/Chroma RAG 与 TF-IDF 回退
│   │   ├── business_closure_service.py      # 预警、工单、报告、行动项闭环聚合
│   │   ├── deepseek_client.py               # 大模型调用封装，密钥从环境变量读取
│   │   └── *_service.py                     # 各智能体对应的业务计算服务
│   ├── schemas/                             # Pydantic 输入/输出模型
│   │   ├── agent.py                         # 通用智能体请求与响应结构
│   │   ├── business_closure.py              # 业务闭环对象结构
│   │   └── *_management.py / *_optimization.py # 各业务域数据模型
│   ├── models/                              # SQLAlchemy 数据模型
│   │   └── agent_run.py                     # 智能体运行记录
│   ├── db/                                  # 数据库连接与会话
│   │   ├── base.py
│   │   └── session.py
│   ├── core/                                # 配置、日志与安全护栏
│   │   ├── config.py                        # 环境变量配置入口
│   │   ├── guardrails.py                    # 敏感规则与禁止模式
│   │   └── logging.py
│   └── memory/                              # 本地记忆存储封装
├── frontend/                                # 前端 Vue3 + Element Plus 工程
│   ├── package.json                         # 前端依赖与脚本
│   ├── vite.config.ts                       # Vite 构建配置
│   └── src/
│       ├── main.ts                          # 前端入口
│       ├── router.ts                        # 页面路由
│       ├── App.vue                          # 根组件
│       ├── api/                             # 后端 API 调用封装
│       ├── components/
│       │   ├── AppLayout.vue                # 企业后台整体布局
│       │   └── AgentResult.vue              # 智能分析结果、路径图、证据展示
│       ├── services/                        # 登录、历史记录、演示数据等前端服务
│       ├── types/                           # 前端 TypeScript 类型
│       └── views/                           # 业务页面
│           ├── LoginView.vue                # 登录页
│           ├── RegisterView.vue             # 注册页
│           ├── DashboardView.vue            # 运营总览
│           ├── WorkspaceView.vue            # 智能体工作台
│           ├── BusinessAgentView.vue        # 生产/质量/设备/供应链/工艺业务页
│           ├── ClosureCenterView.vue        # 业务闭环中心
│           ├── HistoryView.vue              # 历史记录
│           └── ProfileView.vue              # 个人中心
├── tests/                                   # 自动化测试
│   ├── test_orchestrator.py                 # 编排器、路由、协同、答案质量门测试
│   ├── test_business_answer_service.py      # 业务答案增强测试
│   ├── test_*_agent.py                      # 五个智能体单元测试
│   ├── test_knowledge_rag.py                # RAG/知识检索测试
│   ├── test_business_closure.py             # 业务闭环测试
│   ├── test_integration.py                  # 接口集成测试
│   └── test_guardrails.py                   # 安全护栏测试
├── docs/                                    # 项目讲解与流程文档
│   ├── agent_flowcharts.md                  # 5 个智能体 Mermaid 流程图
│   ├── video_script.md                      # 项目讲解视频逐字稿
│   └── reports/                             # 项目日报/过程材料
├── hooks/
│   └── check_claude.py                      # 提交前安全与规范扫描
├── README.md                                # 项目总说明与接口说明
├── START.md                                 # 一键启动、清缓存重启、健康检查
├── frontend/DEMO_SCRIPT.md                  # 前端演示讲解脚本
├── frontend/README.md                       # 前端模块说明
├── AGENTS.md / CLAUDE.md                    # 协作规则与敏感模块指针
├── MEMORY.md                                # 项目过程记忆与验收记录
├── .env.example                             # 环境变量示例，真实 .env 不提交
├── pyproject.toml                           # Python 项目配置
├── uv.lock                                  # Python 依赖锁定文件
├── start-dev.bat                            # Windows 一键启动入口
└── start-dev.ps1                            # 一键启动 PowerShell 实现
```
