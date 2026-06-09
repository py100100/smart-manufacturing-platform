from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

# ── 枚举 ──────────────────────────────────────────────────────────

Priority = Literal["urgent", "high", "medium", "low"]
OptimizationGoal = Literal["delivery_first", "balanced"]
POStatus = Literal["in_transit", "received", "delayed", "cancelled", "confirmed"]
SupplierStatus = Literal["active", "suspended", "under_review"]
SupplierRiskLevel = Literal["low", "medium", "high"]
NodeResultStatus = Literal["success", "warning", "failed"]

AgentDecision = Literal[
    "supply_chain_stable",
    "shortage_risk_detected",
    "critical_shortage",
    "purchase_recommended",
    "overstock_risk_detected",
    "supplier_risk_detected",
    "po_delay_risk",
    "data_insufficient",
]


# ══════════════════════════════════════════════════════════════════
# 输入数据结构
# ══════════════════════════════════════════════════════════════════


class ProductionPlanItem(BaseModel):
    """生产计划条目"""

    plan_id: str = Field(default="", description="计划编号")
    product_id: str = Field(..., description="产品编号")
    quantity: int = Field(..., gt=0, description="计划产量")
    start_date: date | str = Field(..., description="计划开始日期")
    due_date: date | str = Field(..., description="交付日期")
    priority: Priority = Field(default="medium", description="优先级")


class BOMMaterial(BaseModel):
    """BOM 子物料条目"""

    material_id: str = Field(..., description="物料编号")
    material_name: str = Field(default="", description="物料名称")
    required_quantity_per_unit: float = Field(..., gt=0, description="单位产品所需物料数量")
    unit: str = Field(default="", description="物料单位")


class BOMEntry(BaseModel):
    """物料清单条目（按产品聚合）。

    支持两种输入格式：

    1. 嵌套格式（内部标准）：
       {"product_id": "P-001", "materials": [{"material_id": "M-001", ...}]}

    2. 扁平格式（任务书原始样例）：
       {"product_id": "P-001", "material_id": "M-001",
        "quantity_per_unit": 2.0, "material_name": "...", "unit": "kg"}
       扁平格式会自动展开为嵌套格式。
    """

    bom_id: str = Field(default="", description="BOM 条目编号")
    product_id: str = Field(..., description="产品编号")
    materials: list[BOMMaterial] = Field(
        default_factory=list, description="该产品所需的物料列表"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_flat_to_nested(cls, data: Any) -> Any:
        """将扁平 BOM 格式自动转换为嵌套格式。"""
        if isinstance(data, dict):
            has_flat_fields = "material_id" in data or "quantity_per_unit" in data
            has_materials = "materials" in data
            if has_flat_fields and not has_materials:
                material: dict[str, Any] = {
                    "material_id": data.pop("material_id", ""),
                    "material_name": data.pop("material_name", ""),
                    "required_quantity_per_unit": data.pop(
                        "quantity_per_unit",
                        data.pop("required_quantity_per_unit", 0.0),
                    ),
                    "unit": data.pop("unit", ""),
                }
                data["materials"] = [material]
        return data


class InventoryItem(BaseModel):
    """库存条目"""

    material_id: str = Field(..., description="物料编号")
    material_name: str = Field(default="", description="物料名称")
    available_quantity: float = Field(default=0.0, ge=0, description="可用库存量")
    reserved: float = Field(
        default=0.0, ge=0,
        validation_alias=AliasChoices("reserved", "reserved_quantity"),
        description="已预留量",
    )
    safety_stock: float = Field(default=0.0, ge=0, description="安全库存量")
    max_stock: float | None = Field(default=None, ge=0, description="最大库存量（超出视为积压）")
    unit: str = Field(default="", description="单位")
    unit_cost: float = Field(default=0.0, ge=0, description="单位成本")
    lead_time_days: int = Field(default=0, ge=0, description="采购前置时间（天）")


class PurchaseOrderItem(BaseModel):
    """在途采购单条目"""

    po_id: str = Field(..., description="采购单编号")
    material_id: str = Field(..., description="物料编号")
    supplier_id: str = Field(default="", description="供应商编号")
    order_quantity: float = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices(
            "order_quantity", "quantity", "qty", "order_qty", "purchase_quantity",
            "ordered_quantity",
        ),
        description="采购数量",
    )
    ordered_date: date | str | None = Field(default=None, description="下单日期")
    expected_delivery_date: date | str = Field(
        ...,
        validation_alias=AliasChoices(
            "expected_delivery_date", "delivery_date", "expected_date", "due_date",
            "expected_delivery", "arrival_date", "expected_arrival_date",
        ),
        description="预计到货日期",
    )
    status: POStatus = Field(default="in_transit", description="采购单状态")
    received_quantity: float = Field(default=0.0, ge=0, description="已收货数量")


class SupplierInfo(BaseModel):
    """供应商信息"""

    supplier_id: str = Field(..., description="供应商编号")
    supplier_name: str = Field(default="", description="供应商名称")
    material_ids: list[str] = Field(default_factory=list, description="可供应物料列表")
    on_time_delivery_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="准时交货率 (0-1)"
    )
    quality_pass_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        validation_alias=AliasChoices("quality_pass_rate", "quality_score"),
        description="质量合格率 (0-1)，任务书字段 quality_score",
    )
    price_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="价格评分 (0-1)，任务书字段 price_score",
    )
    lead_time_days: int = Field(default=0, ge=0, description="平均供货周期（天）")
    unit_price: float = Field(default=0.0, ge=0, description="物料单价（备选，优先使用 price_score）")
    risk_level: SupplierRiskLevel = Field(
        default="low",
        validation_alias=AliasChoices("risk_level", "status"),
        description="供应商风险等级，任务书字段 risk_level",
    )
    status: SupplierStatus = Field(default="active", description="供应商状态")
    cooperation_years: float = Field(default=0.0, ge=0, description="合作年限")


# ══════════════════════════════════════════════════════════════════
# 智能体请求
# ══════════════════════════════════════════════════════════════════


class SupplyChainManagementRequest(BaseModel):
    """供应链协同管理智能体入参"""

    production_plan: list[ProductionPlanItem] = Field(
        default_factory=list, description="生产计划列表"
    )
    bill_of_materials: list[BOMEntry] = Field(
        default_factory=list, description="物料清单 (BOM)"
    )
    inventory: list[InventoryItem] = Field(
        default_factory=list, description="库存列表"
    )
    purchase_orders: list[PurchaseOrderItem] = Field(
        default_factory=list, description="在途采购单列表"
    )
    suppliers: list[SupplierInfo] = Field(
        default_factory=list, description="供应商列表"
    )
    optimization_goal: OptimizationGoal = Field(
        default="delivery_first", description="优化目标"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_constraints(cls, data: Any) -> Any:
        """将任务书 constraints.optimize_for 映射到 optimization_goal。"""
        if isinstance(data, dict):
            constraints = data.pop("constraints", None)
            if isinstance(constraints, dict):
                opt = constraints.get("optimize_for")
                if opt is not None and "optimization_goal" not in data:
                    data["optimization_goal"] = opt
        return data


# ══════════════════════════════════════════════════════════════════
# 输出数据结构
# ══════════════════════════════════════════════════════════════════


class MaterialDemand(BaseModel):
    """物料需求计算结果"""

    material_id: str
    material_name: str = ""
    required_quantity: float = 0.0
    unit: str = ""
    source_plans: list[str] = Field(default_factory=list)


class InventoryAssessment(BaseModel):
    """库存评估结果"""

    material_id: str
    available_quantity: float = 0.0
    reserved: float = 0.0
    useable_quantity: float = 0.0  # available - reserved
    safety_stock: float = 0.0
    in_transit_on_time: float = 0.0  # 在途按期到货量
    projected_available: float = 0.0  # useable + in_transit_on_time
    required_quantity: float = 0.0
    shortage_quantity: float = 0.0
    overstock_quantity: float = 0.0
    max_stock: float | None = None
    turnover_rate: float = 0.0
    status: str = "normal"


class PurchaseRecommendation(BaseModel):
    """采购建议"""

    material_id: str
    material_name: str = ""
    recommended_quantity: float = 0.0
    recommended_supplier_id: str = ""
    recommended_supplier_name: str = ""
    unit_price: float = 0.0
    estimated_cost: float = 0.0
    lead_time_days: int = 0
    urgency: Priority = "medium"
    reason: str = ""


class SupplierEvaluation(BaseModel):
    """供应商评估结果"""

    supplier_id: str
    supplier_name: str = ""
    on_time_rate: float = 0.0
    quality_rate: float = 0.0
    lead_time_days: int = 0
    unit_price: float = 0.0
    composite_score: float = 0.0
    risk_level: str = "low"
    recommendation: str = ""


class PODelayRisk(BaseModel):
    """采购单延期风险"""

    po_id: str
    material_id: str
    supplier_id: str = ""
    expected_delivery_date: str = ""
    status: str = ""
    delay_days: int = 0
    risk_level: str = "low"
    impact: str = ""


class TurnoverAnalysis(BaseModel):
    """库存周转分析"""

    material_id: str
    annual_demand: float = 0.0
    average_inventory: float = 0.0
    turnover_rate: float = 0.0
    turnover_days: float = 0.0
    assessment: str = ""


class CoordinationAction(BaseModel):
    """协同行动建议"""

    action_type: str = ""  # purchase / transfer / expedite / reduce / monitor
    material_id: str = ""
    from_source: str = ""  # 来源（供应商/仓库/产线）
    to_target: str = ""  # 目标（产线/仓库）
    quantity: float = 0.0
    suggested_timing: str = ""
    reason: str = ""


class SupplyChainNodeFeedback(BaseModel):
    """节点反馈"""

    node: str = Field(..., description="节点标识")
    status: NodeResultStatus = Field(..., description="节点状态")
    message: str = Field(..., description="节点反馈信息")


class SupplyChainManagementOutput(BaseModel):
    """供应链协同管理智能体标准输出"""

    summary: str = Field(..., description="分析摘要")
    decision: AgentDecision = Field(..., description="智能体决策")
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    node_feedback: list[SupplyChainNodeFeedback] = Field(default_factory=list)
    material_demands: list[MaterialDemand] = Field(default_factory=list)
    inventory_assessments: list[InventoryAssessment] = Field(default_factory=list)
    purchase_recommendations: list[PurchaseRecommendation] = Field(default_factory=list)
    supplier_evaluations: list[SupplierEvaluation] = Field(default_factory=list)
    po_delay_risks: list[PODelayRisk] = Field(default_factory=list)
    turnover_analyses: list[TurnoverAnalysis] = Field(default_factory=list)
    coordination_actions: list[CoordinationAction] = Field(default_factory=list)
