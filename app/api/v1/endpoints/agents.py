"""智能体 API 端点。

接口层只做入参校验和编排调用，复杂逻辑在 services / agents。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.agents.registry import get_registry
from app.db.session import get_db
from app.schemas.agent import AgentName, AgentTaskRequest
from app.schemas.business_closure import OrchestrationWithClosure
from app.services.business_closure_service import BusinessClosureService
from app.services.orchestrator import AgentOrchestrator

router = APIRouter(prefix="/agents", tags=["agents"])
orchestrator = AgentOrchestrator()
closure_service = BusinessClosureService()
DbSession = Annotated[Session, Depends(get_db)]


def _build_response(orch_response) -> OrchestrationWithClosure:
    """将编排响应包装为业务闭环响应。"""
    closure = closure_service.build_closure(orch_response)
    return OrchestrationWithClosure(
        trace_id=orch_response.trace_id,
        request_text=orch_response.request_text,
        execution_mode=orch_response.execution_mode,
        detected_scenes=orch_response.detected_scenes,
        agent_name=orch_response.agent_name,
        summary=orch_response.summary,
        decision=orch_response.decision,
        evidence=orch_response.evidence,
        next_actions=orch_response.next_actions,
        agent_chain=[s.model_dump() for s in orch_response.agent_chain],
        node_feedback=[n.model_dump() for n in orch_response.node_feedback],
        token_usage=orch_response.token_usage,
        closure=closure,
    )


# ══════════════════════════════════════════════════════════════════
# 统一执行入口
# ══════════════════════════════════════════════════════════════════


@router.post("/execute", response_model=OrchestrationWithClosure)
async def execute_agent_task(
    request: AgentTaskRequest,
    db: DbSession,
) -> OrchestrationWithClosure:
    """统一智能体执行入口。

    自动检测业务场景，路由到最匹配的智能体（单/多智能体协同），
    返回编排链路 + 业务闭环对象（预警、工单、报告、行动项）。
    """
    orch_response = await orchestrator.execute(request=request, db=db)
    return _build_response(orch_response)


# ══════════════════════════════════════════════════════════════════
# 按智能体直接调用
# ══════════════════════════════════════════════════════════════════


@router.post("/{agent_name}/execute", response_model=OrchestrationWithClosure)
async def execute_named_agent(
    agent_name: Annotated[
        AgentName,
        Path(description="智能体名称"),
    ],
    request: AgentTaskRequest,
    db: DbSession,
) -> OrchestrationWithClosure:
    """直接调用指定智能体（跳过场景检测和路由）。

    路径参数 agent_name 必须是已注册的智能体名称。
    """
    # 强制覆盖请求中的 agent_name
    request.agent_name = agent_name
    orch_response = await orchestrator.execute(request=request, db=db)
    return _build_response(orch_response)


# ══════════════════════════════════════════════════════════════════
# 查询可用智能体
# ══════════════════════════════════════════════════════════════════


@router.get("/")
async def list_agents() -> list[dict]:
    """列出所有已注册智能体及其元数据。"""
    registry = get_registry()
    return [
        {
            "name": meta.name,
            "display_name": meta.display_name,
            "scenario_hint": meta.scenario_hint,
            "input_schema": meta.input_schema,
            "output_schema": meta.output_schema,
        }
        for meta in registry.all_meta()
    ]
