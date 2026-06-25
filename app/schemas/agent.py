from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal[
    "production_scheduling",
    "quality_inspection",
    "predictive_maintenance",
    "supply_chain_management",
    "process_parameter_optimization",
]
NodeStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class NodeFeedback(BaseModel):
    node_id: str
    node_name: str
    status: NodeStatus
    detail: str
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0


class AgentTaskRequest(BaseModel):
    request_text: str = Field(min_length=3, max_length=2000)
    agent_name: AgentName | None = None
    context: dict[str, str] = Field(default_factory=dict)
    require_llm: bool = True


class AgentTaskResponse(BaseModel):
    """单智能体调用响应"""

    trace_id: str
    agent_name: str
    summary: str
    decision: str
    evidence: list[str]
    next_actions: list[str]
    node_feedback: list[NodeFeedback]
    model_used: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    memory_updated: bool = False


class AgentStep(BaseModel):
    """多智能体链中的单个执行步骤"""

    agent_name: str
    display_name: str
    status: NodeStatus = "completed"
    summary: str = ""
    decision: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    node_feedback: list[NodeFeedback] = Field(default_factory=list)


class OrchestrationResponse(BaseModel):
    """多智能体协同调用响应 — 包含完整执行链路"""

    trace_id: str
    request_text: str
    detected_scenes: list[str] = Field(
        default_factory=list, description="识别到的业务场景列表"
    )
    execution_mode: str = Field(
        default="single", description="single | collaborative"
    )
    # 单智能体兼容
    agent_name: str = ""
    summary: str = ""
    decision: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    # 多智能体链路
    agent_chain: list[AgentStep] = Field(
        default_factory=list, description="执行链路，按调用顺序排列"
    )
    # 聚合节点反馈（所有 agent 的合并视图）
    node_feedback: list[NodeFeedback] = Field(
        default_factory=list, description="聚合所有智能体的节点反馈"
    )
    model_used: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    memory_updated: bool = False


class HealthResponse(BaseModel):
    app_name: str
    version: str
    database_ready: bool
    model_ready: bool
    graph_ready: bool = False
