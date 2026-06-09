# CLAUDE

## 1. 角色与工作方式

- 先搭基础框架，再逐个完成智能体，前一个验通后再进入下一个。
- 输出必须结构化，可追溯，可在接口层看到节点式反馈。
- 只在需要处使用外部依赖，优先做企业工程中的清晰模块边界。

## 2. 指针而非图书馆

- 项目方案指针：`基于Agentic RAG与多智能体协作智能制造服务平台.md`
- 跨会话记忆指针：`MEMORY.md`
- Hook 规则入口：`hooks/check_claude.py`
- 敏感模块指针：`app/core/config.py`、`app/db/session.py`、`app/services/deepseek_client.py`

## 3. 禁止清单

- 禁止把真实密钥、口令、令牌写入源码。
- 禁止使用 `eval(`、`exec(`、硬编码 `sk-` 风格密钥。
- 禁止在敏感模块中打印配置、密钥、完整模型响应。
- 禁止跨模块堆逻辑，接口层只做入参校验和编排调用。
- 禁止在未验证上一个智能体前继续叠加新功能。

## 4. 5秒可判定规则

- 每个 Python 文件职责单一，文件名与模块职责一致。
- 每个接口只做一件事，复杂逻辑进入 `services` 或 `agents`。
- 每个智能体输出必须包含 `summary`、`decision`、`evidence`、`next_actions`、`node_feedback`。
- 敏感模块变更必须能被 `python hooks/check_claude.py` 快速扫描。
- `CLAUDE.md` 只存规则和指针，不沉淀业务知识。
- 跨会话记忆只写入 `MEMORY.md` 一个文件。

## 5. Hook 驱动

- 提交前运行：`python hooks/check_claude.py`
- 扫描目标：默认扫描 `app`、`hooks`、`tests`
- 判定目标：在 5 秒内发现禁止模式、敏感模块改动提示、基础风格违规

## 6. 敏感模块护栏

- `app/core/config.py`：只允许读取环境变量和派生配置。
- `app/db/session.py`：只允许通过配置构造数据库连接。
- `app/services/deepseek_client.py`：只允许通过环境变量访问模型服务。
- `hooks/check_claude.py`：保持轻量、快速、可离线执行。
