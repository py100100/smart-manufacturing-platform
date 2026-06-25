"""业务闭环对象 — 将智能体输出转化为可执行的企业业务实体。

- 预警 Alert：安全/质量/供应链/设备/工艺风险感知
- 工单 WorkOrder：维护/采购/优化/质检等可执行工单
- 报告 Report：结构化分析报告
- 后续行动 ActionItem：可跟踪的后续行动项
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.agent import TokenUsage


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


# ── 枚举 ──────────────────────────────────────────────────────────

AlertSeverity = Literal["critical", "warning", "info"]
AlertType = Literal["safety", "quality", "supply", "maintenance", "process"]
WorkOrderType = Literal["maintenance", "purchase", "optimization", "inspection"]
WorkOrderPriority = Literal["urgent", "high", "medium", "low"]
ActionItemStatus = Literal["pending", "in_progress", "completed", "cancelled"]


# ══════════════════════════════════════════════════════════════════
# 业务对象
# ══════════════════════════════════════════════════════════════════


class Alert(BaseModel):
    """预警 — 当智能体检测到风险时自动生成。"""

    alert_id: str = Field(default_factory=lambda: _uid("ALERT"))
    source_agent: str = Field(..., description="来源智能体名称")
    severity: AlertSeverity = Field(..., description="严重等级")
    alert_type: AlertType = Field(..., description="预警类型")
    title: str = Field(..., description="预警标题")
    message: str = Field(..., description="预警详情")
    generated_at: datetime = Field(default_factory=_now)
    acknowledged: bool = Field(default=False, description="是否已确认")


class WorkOrder(BaseModel):
    """工单 — 需要人员执行的维护/采购/优化/质检任务。"""

    order_id: str = Field(default_factory=lambda: _uid("WO"))
    source_agent: str = Field(..., description="来源智能体")
    order_type: WorkOrderType = Field(..., description="工单类型")
    title: str = Field(..., description="工单标题")
    description: str = Field(default="", description="描述")
    priority: WorkOrderPriority = Field(default="medium", description="优先级")
    target_entity: str = Field(
        default="", description="目标实体 — 设备ID/物料ID/参数名称"
    )
    suggested_timing: str = Field(default="", description="建议执行时间窗口")
    status: str = Field(default="pending", description="工单状态")
    created_at: datetime = Field(default_factory=_now)


class Report(BaseModel):
    """分析报告 — 汇总智能体分析结论的结构化报告。"""

    report_id: str = Field(default_factory=lambda: _uid("RPT"))
    source_agents: list[str] = Field(
        default_factory=list, description="来源智能体列表"
    )
    title: str = Field(..., description="报告标题")
    summary: str = Field(..., description="分析摘要")
    findings: list[str] = Field(default_factory=list, description="发现项")
    recommendations: list[str] = Field(
        default_factory=list, description="建议项"
    )
    generated_at: datetime = Field(default_factory=_now)


class ActionItem(BaseModel):
    """后续行动项 — 从智能体 next_actions 拆解的单个可追踪任务。"""

    item_id: str = Field(default_factory=lambda: _uid("ACT"))
    source_agent: str = Field(..., description="来源智能体")
    description: str = Field(..., description="行动描述")
    priority: WorkOrderPriority = Field(default="medium")
    status: ActionItemStatus = Field(default="pending")
    created_at: datetime = Field(default_factory=_now)
    due_date: datetime | None = Field(default=None, description="建议完成时间")


# ══════════════════════════════════════════════════════════════════
# 业务闭环响应
# ══════════════════════════════════════════════════════════════════


class BusinessClosure(BaseModel):
    """业务闭环 — 聚合预警、工单、报告、行动项。"""

    alerts: list[Alert] = Field(default_factory=list)
    work_orders: list[WorkOrder] = Field(default_factory=list)
    reports: list[Report] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class OrchestrationWithClosure(BaseModel):
    """编排响应 + 业务闭环 — 接口层一次性返回完整业务视图。"""

    # 编排层（来自 OrchestrationResponse）
    trace_id: str = ""
    request_text: str = ""
    execution_mode: str = ""
    detected_scenes: list[str] = Field(default_factory=list)
    agent_name: str = ""
    summary: str = ""
    decision: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    agent_chain: list = Field(default_factory=list)
    node_feedback: list = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    # 业务闭环
    closure: BusinessClosure = Field(default_factory=BusinessClosure)
