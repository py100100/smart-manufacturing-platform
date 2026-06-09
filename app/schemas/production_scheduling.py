from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agent import NodeFeedback

# ── 输入数据结构 ──────────────────────────────────────────────


class OrderInput(BaseModel):
    """订单输入"""

    order_id: str = Field(..., description="订单编号，如 ORD-001")
    product_id: str = Field(..., description="产品编号，如 P-1001")
    quantity: int = Field(..., gt=0, description="生产数量")
    due_date: date = Field(..., description="交期")
    priority: Literal["high", "medium", "low"] = Field(default="medium", description="优先级")


class WorkOrderInput(BaseModel):
    """工单输入"""

    work_order_id: str = Field(..., description="工单编号，如 WO-001")
    order_id: str = Field(..., description="所属订单编号")
    product_id: str = Field(..., description="产品编号")
    quantity: int = Field(..., gt=0, description="工单数量")


class ProcessStepInput(BaseModel):
    """工艺步骤"""

    step_id: str = Field(..., description="步骤编号")
    step_name: str = Field(..., description="步骤名称，如 CNC 加工")
    sequence: int = Field(..., ge=1, description="工序顺序")
    standard_minutes_per_unit: float = Field(..., gt=0, description="单件标准工时（分钟）")
    equipment_types: list[str] = Field(
        default_factory=list, description="所需设备类型列表"
    )


class ProcessRouteInput(BaseModel):
    """工艺路线"""

    route_id: str = Field(..., description="路线编号")
    product_id: str = Field(..., description="适用产品编号")
    product_name: str = Field(default="", description="产品名称")
    steps: list[ProcessStepInput] = Field(..., min_length=1, description="工艺步骤列表")


class EquipmentInput(BaseModel):
    """设备/机器"""

    equipment_id: str = Field(..., description="设备编号")
    equipment_name: str = Field(..., description="设备名称")
    equipment_type: str = Field(..., description="设备类型")
    status: Literal["available", "maintenance", "offline"] = Field(
        default="available", description="设备状态"
    )
    available_minutes_per_day: int = Field(..., gt=0, description="每日可用分钟数")
    cost_per_hour: float = Field(..., gt=0, description="每小时成本")


class MaterialConstraintInput(BaseModel):
    """物料约束"""

    material_id: str = Field(..., description="物料编号")
    product_id: str = Field(..., description="适用产品编号")
    available_quantity: int = Field(..., ge=0, description="可用数量")
    required_per_unit: float = Field(..., gt=0, description="单件用量")


Priority = Literal["high", "medium", "low"]
OptimizationGoal = Literal["delivery_first", "cost_first", "capacity_balance"]


class SchedulingConstraints(BaseModel):
    """调度约束条件。

    兼容任务书中的 constraints.optimize_for / working_days / allow_overtime。
    """

    optimize_for: OptimizationGoal = Field(
        default="delivery_first",
        description="优化目标，与顶层 optimization_goal 等效",
    )
    working_days: int = Field(
        default=0,
        ge=0,
        description=(
            "可用工作天数。为 0 时由 service 根据订单交期自动推算；"
            "大于 0 时强制使用该值计算产能窗口，不得依赖 date.today()。"
        ),
    )
    allow_overtime: bool = Field(
        default=False,
        description="是否允许加班以扩展可用产能",
    )


class SchedulingRequest(BaseModel):
    """调度请求 —— 智能体入参"""

    orders: list[OrderInput] = Field(..., min_length=1, description="订单列表")
    work_orders: list[WorkOrderInput] = Field(..., min_length=1, description="工单列表")
    process_routes: list[ProcessRouteInput] = Field(..., min_length=1, description="工艺路线列表")
    equipment: list[EquipmentInput] = Field(..., min_length=1, description="设备列表")
    material_constraints: list[MaterialConstraintInput] = Field(
        default_factory=list, description="物料约束（可选）"
    )
    optimization_goal: OptimizationGoal = Field(
        default="delivery_first", description="优化目标"
    )
    constraints: SchedulingConstraints = Field(
        default_factory=SchedulingConstraints,
        description="调度约束（工作天数、加班等）",
    )


# ── 输出数据结构 ──────────────────────────────────────────────

ScheduleItemStatus = Literal["scheduled", "delayed", "capacity_risk", "unavailable"]


class ScheduleItem(BaseModel):
    """单个排程条目"""

    work_order_id: str
    order_id: str
    product_id: str
    step_id: str
    step_name: str
    sequence: int
    equipment_id: str
    equipment_name: str
    quantity: int
    standard_minutes_per_unit: float
    total_minutes: float
    start_minute: float
    end_minute: float
    status: ScheduleItemStatus
    status_reason: str = ""


class BottleneckInfo(BaseModel):
    """瓶颈信息"""

    equipment_id: str
    equipment_name: str
    total_load_minutes: float
    available_minutes: float
    utilization: float
    severity: Literal["normal", "warning", "critical"]


class SchedulingResult(BaseModel):
    """完整调度结果"""

    schedule: list[ScheduleItem] = Field(default_factory=list)
    bottlenecks: list[BottleneckInfo] = Field(default_factory=list)
    total_orders: int = 0
    scheduled_orders: int = 0
    delayed_orders: int = 0
    overall_feasibility: Literal["feasible", "risk_detected", "infeasible"] = "feasible"


AgentDecision = Literal[
    "schedule_approved",
    "schedule_risk_detected",
    "capacity_insufficient",
    "route_missing",
    "machine_unavailable",
]


class SchedulingAgentOutput(BaseModel):
    """智能体标准输出"""

    summary: str
    decision: AgentDecision
    evidence: list[str]
    next_actions: list[str]
    node_feedback: list[NodeFeedback]
    schedule_detail: SchedulingResult
