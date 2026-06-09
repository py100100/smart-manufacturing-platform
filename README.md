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

智能体编排仍由自研 `AgentOrchestrator` 负责：自动路由、指定智能体调用、多智能体协同链路与节点反馈聚合。

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
| `summary` | string | 分析摘要 |
| `decision` | string | 智能体决策 |
| `evidence` | list[string] | 支撑证据（含 `[knowledge:来源]` 知识库标记） |
| `next_actions` | list[string] | 建议后续行动 |
| `node_feedback` | list[object] | 聚合所有智能体的节点式反馈 |
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
```

## 项目结构

```
app/
├── api/v1/endpoints/    # 接口层（只做入参校验和编排调用）
├── agents/              # 五个业务智能体
├── services/            # 编排、知识/RAG、业务闭环
├── schemas/             # Pydantic 输入/输出模型
├── core/                # 配置、日志
├── db/                  # 数据库连接
hooks/
tests/
MEMORY.md                # 跨会话记忆
```
