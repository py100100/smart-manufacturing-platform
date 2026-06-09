from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

# ── 枚举 ──────────────────────────────────────────────────────────

OptimizeFor = Literal["quality_first", "efficiency_first", "balanced"]

AgentDecision = Literal[
    "safety_risk_detected",
    "parameter_out_of_range",
    "insufficient_history_data",
    "conflicting_targets",
    "quality_risk_detected",
    "optimization_recommended",
    "parameters_optimal",
]

NodeResultStatus = Literal["success", "warning", "failed"]

CorrelationTrend = Literal[
    "positive_quality_correlation",
    "negative_quality_correlation",
    "neutral",
    "efficiency_tradeoff",
]

QualityFeedbackSeverity = Literal["critical", "major", "minor", "info"]


# ══════════════════════════════════════════════════════════════════
# 输入数据结构
# ══════════════════════════════════════════════════════════════════


class ProcessInfo(BaseModel):
    """工艺基本信息"""

    process_id: str = Field(..., description="工艺编号")
    process_name: str = Field(default="", description="工艺名称")
    product_id: str = Field(default="", description="产品编号")
    process_step: str = Field(default="", description="工艺步骤")


class ParameterConstraint(BaseModel):
    """参数约束定义"""

    parameter_name: str = Field(..., description="参数名称")
    min_value: float = Field(..., description="最小允许值")
    max_value: float = Field(..., description="最大允许值")
    safety_critical: bool = Field(default=False, description="是否为安全关键参数")
    unit: str = Field(default="", description="单位")


class CurrentParameter(BaseModel):
    """当前工艺参数"""

    parameter_name: str = Field(..., description="参数名称")
    value: float = Field(..., description="当前值")


class HistoricalBatch(BaseModel):
    """历史生产批次。

    支持两种输入格式：
    1. 扁平格式：yield_rate / defect_rate / cycle_time_minutes / throughput_per_hour
    2. 任务书嵌套格式：
       "quality_metrics": {"yield_rate": ..., "defect_rate": ..., "quality_score": ...}
       "production_metrics": {"cycle_time_minutes": ..., "throughput_per_hour": ...}
    """

    batch_id: str = Field(..., description="批次编号")
    timestamp: datetime | str | None = Field(default=None, description="批次时间戳")
    parameters: dict[str, float] = Field(
        default_factory=dict, description="工艺参数键值对"
    )
    yield_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="良品率 (0-1)")
    defect_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="缺陷率 (0-1)")
    cycle_time_minutes: float = Field(default=0.0, ge=0, description="单件节拍（分钟）")
    throughput_per_hour: float = Field(default=0.0, ge=0, description="每小时产出")
    dimension_deviation: float = Field(default=0.0, ge=0, description="尺寸偏差")
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0, description="质量综合评分 (0-1)")
    quality_passed: bool = Field(default=True, description="质量是否达标")

    @model_validator(mode="before")
    @classmethod
    def _normalize_nested_metrics(cls, data: Any) -> Any:
        """将任务书 quality_metrics / production_metrics 展开到扁平字段。"""
        if isinstance(data, dict):
            qm = data.pop("quality_metrics", None)
            if isinstance(qm, dict):
                for key in ("yield_rate", "defect_rate", "quality_score",
                            "dimension_deviation", "quality_passed"):
                    if key in qm and key not in data:
                        data[key] = qm[key]
            pm = data.pop("production_metrics", None)
            if isinstance(pm, dict):
                for key in ("cycle_time_minutes", "throughput_per_hour"):
                    if key in pm and key not in data:
                        data[key] = pm[key]
        return data


class QualityFeedback(BaseModel):
    """质量反馈记录"""

    batch_id: str = Field(default="", description="关联批次")
    feedback_text: str = Field(default="", description="反馈文本")
    issues: list[str] = Field(default_factory=list, description="问题列表")
    severity: QualityFeedbackSeverity = Field(default="info", description="严重程度")


class OptimizationConfig(BaseModel):
    """优化配置"""

    optimize_for: OptimizeFor = Field(default="balanced", description="优化目标")
    min_yield_rate: float = Field(default=0.9, ge=0.0, le=1.0, description="最低良品率目标")
    max_defect_rate: float = Field(default=0.05, ge=0.0, le=1.0, description="最高缺陷率目标")
    target_cycle_time_minutes: float = Field(
        default=0.0, ge=0, description="目标节拍（分钟），0 表示不限"
    )


# ══════════════════════════════════════════════════════════════════
# 智能体请求
# ══════════════════════════════════════════════════════════════════


class ProcessParameterOptimizationRequest(BaseModel):
    """工艺参数优化智能体入参"""

    process: ProcessInfo = Field(..., description="工艺信息")
    historical_batches: list[HistoricalBatch] = Field(
        default_factory=list, description="历史生产批次"
    )
    parameter_constraints: list[ParameterConstraint] = Field(
        default_factory=list, description="参数约束列表"
    )
    current_parameters: list[CurrentParameter] = Field(
        default_factory=list, description="当前工艺参数"
    )
    quality_feedback: list[QualityFeedback] = Field(
        default_factory=list, description="质量反馈记录"
    )
    optimization_config: OptimizationConfig = Field(
        default_factory=OptimizationConfig,
        validation_alias=AliasChoices("optimization_config", "quality_targets"),
        description="优化配置，任务书字段 quality_targets",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_request_fields(cls, data: Any) -> Any:
        """处理任务书格式兼容。

        1. current_parameters 支持 dict → 转为 list[CurrentParameter]
        2. quality_targets 已在 Field alias 中处理
        """
        if isinstance(data, dict):
            # current_parameters: dict → list
            cp = data.get("current_parameters")
            if isinstance(cp, dict):
                data["current_parameters"] = [
                    {"parameter_name": k, "value": v} for k, v in cp.items()
                ]
        return data


# ══════════════════════════════════════════════════════════════════
# 输出数据结构
# ══════════════════════════════════════════════════════════════════


class ParameterCorrelation(BaseModel):
    """参数-质量相关性分析结果"""

    parameter_name: str = ""
    trend: CorrelationTrend = "neutral"
    description: str = ""
    high_group_avg_yield: float = 0.0
    low_group_avg_yield: float = 0.0
    high_group_avg_defect: float = 0.0
    low_group_avg_defect: float = 0.0


class ConstraintViolation(BaseModel):
    """参数约束违规"""

    parameter_name: str = ""
    current_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    safety_critical: bool = False
    violation_type: str = ""  # "below_min" | "above_max"


class ParameterRecommendation(BaseModel):
    """推荐工艺参数"""

    parameter_name: str = ""
    current_value: float = 0.0
    recommended_value: float = 0.0
    delta: float = 0.0
    unit: str = ""
    clamped: bool = False  # 是否被约束范围 clamp


class ImprovementEstimate(BaseModel):
    """预期改进量"""

    expected_yield_rate_delta: float = 0.0
    expected_defect_rate_delta: float = 0.0
    expected_cycle_time_delta: float = 0.0
    description: str = ""


class ProcessNodeFeedback(BaseModel):
    """节点反馈"""

    node: str = Field(..., description="节点标识")
    status: NodeResultStatus = Field(..., description="节点状态")
    message: str = Field(..., description="节点反馈信息")


class ProcessParameterOptimizationOutput(BaseModel):
    """工艺参数优化智能体标准输出"""

    summary: str = Field(..., description="分析摘要")
    decision: AgentDecision = Field(..., description="智能体决策")
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    node_feedback: list[ProcessNodeFeedback] = Field(default_factory=list)
    parameter_correlations: list[ParameterCorrelation] = Field(default_factory=list)
    constraint_violations: list[ConstraintViolation] = Field(default_factory=list)
    recommended_parameters: list[ParameterRecommendation] = Field(default_factory=list)
    improvement_estimate: ImprovementEstimate | None = None
    best_batch_id: str = ""
    best_batch_score: float = 0.0
    conflicting_targets_detected: bool = False
