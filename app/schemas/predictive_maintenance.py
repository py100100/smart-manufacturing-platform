from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── 枚举 ──────────────────────────────────────────────────────────

SensorStatus = Literal["normal", "warning", "critical"]
RiskLevel = Literal["low", "medium", "high", "critical"]
TrendDirection = Literal["stable", "rising_trend", "falling_trend"]
EquipmentStatus = Literal["running", "stopped", "offline", "maintenance"]
NodeResultStatus = Literal["success", "warning", "failed"]

AgentDecision = Literal[
    "equipment_normal",
    "maintenance_attention_required",
    "failure_risk_detected",
    "critical_failure_risk",
    "maintenance_work_order_required",
    "sensor_data_insufficient",
    "maintenance_rule_missing",
]

SupportedSensorType = Literal["vibration", "temperature", "current", "pressure", "noise"]


# ══════════════════════════════════════════════════════════════════
# 输入数据结构
# ══════════════════════════════════════════════════════════════════


class EquipmentInfo(BaseModel):
    """设备基础信息"""

    equipment_id: str = Field(..., description="设备编号，如 EQ-CNC-001")
    equipment_name: str = Field(default="", description="设备名称")
    equipment_type: str = Field(..., description="设备类型，如 CNC")
    location: str = Field(default="", description="所在位置，如 workshop-A")
    running_status: EquipmentStatus = Field(default="running", description="运行状态")
    last_maintenance_date: datetime | str | None = Field(
        default=None, description="上次维护日期"
    )
    total_runtime_hours: float = Field(default=0.0, ge=0, description="累计运行小时")


class SensorReading(BaseModel):
    """单条传感器读数。

    支持多时间点数据用于趋势分析。
    """

    sensor_id: str = Field(..., description="传感器编号")
    sensor_type: str = Field(..., description="传感器类型：vibration/temperature/current/pressure/noise")
    value: float = Field(..., description="传感器读数")
    unit: str = Field(default="", description="单位")
    timestamp: datetime | str | None = Field(default=None, description="采集时间戳")
    threshold_warning: float | None = Field(default=None, description="警告阈值")
    threshold_critical: float | None = Field(default=None, description="严重阈值")


class HistoricalFailure(BaseModel):
    """历史故障记录"""

    failure_id: str = Field(default="", description="故障记录编号")
    equipment_type: str = Field(..., description="设备类型")
    failure_type: str = Field(..., description="故障类型")
    root_cause: str = Field(default="", description="根因")
    symptoms: list[str] = Field(default_factory=list, description="症状关键词列表")
    mean_time_to_failure_hours: float | None = Field(
        default=None, ge=0, description="平均故障时间（小时）"
    )
    recommended_action: str = Field(default="", description="推荐处理措施")
    occurrence_count: int = Field(default=1, ge=0, description="历史发生次数")
    resolved: bool = Field(default=False, description="是否已解决")


class MaintenanceRule(BaseModel):
    """维护规程"""

    rule_id: str = Field(default="", description="规程编号")
    equipment_type: str = Field(..., description="适用设备类型")
    failure_type: str = Field(..., description="适用故障类型")
    risk_level: RiskLevel = Field(default="low", description="适用风险等级")
    work_order_type: str = Field(default="corrective", description="工单类型")
    priority: str = Field(default="medium", description="优先级")
    required_parts: list[str] = Field(default_factory=list, description="所需备件")
    estimated_duration_hours: float = Field(default=2.0, ge=0, description="预计工时")
    procedure_steps: list[str] = Field(default_factory=list, description="操作步骤")
    maintenance_action: str = Field(default="", description="规程规定的维护动作")
    reference_doc: str = Field(default="", description="参考文档")


# ══════════════════════════════════════════════════════════════════
# 维护上下文
# ══════════════════════════════════════════════════════════════════


class MaintenanceContext(BaseModel):
    """维护现场上下文 —— 影响工单建议和调度优先级。

    每个字段均为可选；提供越完整，工单建议越精确。
    """

    production_criticality: str = Field(
        default="medium",
        description="生产关键性：critical / high / medium / low",
    )
    spare_parts_available: bool = Field(
        default=True, description="所需备件是否在库"
    )
    maintenance_window_hours: float | None = Field(
        default=None, ge=0, description="可用的维护时间窗口（小时）"
    )


# ══════════════════════════════════════════════════════════════════
# 智能体请求
# ══════════════════════════════════════════════════════════════════


class PredictiveMaintenanceRequest(BaseModel):
    """设备预测性维护智能体入参"""

    equipment: EquipmentInfo = Field(..., description="设备信息")
    sensor_readings: list[SensorReading] = Field(
        default_factory=list, description="传感器读数列表"
    )
    historical_failures: list[HistoricalFailure] = Field(
        default_factory=list, description="历史故障记录（可选）"
    )
    maintenance_rules: list[MaintenanceRule] = Field(
        default_factory=list, description="维护规程（可选）"
    )
    context: MaintenanceContext | None = Field(
        default=None,
        description="维护上下文（production_criticality / spare_parts_available / maintenance_window_hours）",
    )
    trend_rise_threshold_pct: float = Field(
        default=20.0, ge=0, description="趋势上升判断阈值（百分比）"
    )


# ══════════════════════════════════════════════════════════════════
# 输出数据结构
# ══════════════════════════════════════════════════════════════════


class SensorEvaluationResult(BaseModel):
    """单个传感器评估结果"""

    sensor_id: str
    sensor_type: str
    value: float
    unit: str = ""
    status: SensorStatus = "normal"
    risk_value: float = 0.0  # 0 / 0.5 / 1.0
    threshold_warning: float | None = None
    threshold_critical: float | None = None


class TrendAnalysisResult(BaseModel):
    """趋势分析结果"""

    sensor_type: str
    direction: TrendDirection = "stable"
    change_pct: float = 0.0
    earliest_value: float = 0.0
    latest_value: float = 0.0
    data_points: int = 0
    alert: bool = False  # 趋势异常标记


class RiskAssessment(BaseModel):
    """综合风险评估"""

    risk_score: float = 0.0
    risk_level: RiskLevel = "low"
    critical_sensors: list[str] = Field(default_factory=list)
    warning_sensors: list[str] = Field(default_factory=list)


class FailurePrediction(BaseModel):
    """故障预测结果"""

    failure_type: str = "unknown_failure"
    root_cause: str = ""
    confidence: float = 0.0
    matched_symptoms: list[str] = Field(default_factory=list)
    mean_time_to_failure_hours: float | None = None
    recommended_action: str = ""
    match_source: str = ""  # "historical" | "rule_based" | "none"


class TimeWindowEstimate(BaseModel):
    """预计故障时间窗口"""

    estimated_window_hours: float | None = None
    window_description: str = ""
    source: str = ""  # "historical" | "risk_based" | "none"


class WorkOrderSuggestion(BaseModel):
    """维护工单建议"""

    work_order_type: str = ""
    equipment_id: str = ""
    failure_type: str = ""
    priority: str = "medium"
    recommended_action: str = ""
    required_parts: list[str] = Field(default_factory=list)
    estimated_duration_hours: float = 0.0
    suggested_start_window: str = ""
    reason: str = ""


class MaintenanceNodeFeedback(BaseModel):
    """节点反馈"""

    node: str = Field(..., description="节点标识")
    status: NodeResultStatus = Field(..., description="节点状态")
    message: str = Field(..., description="节点反馈信息")


class PredictiveMaintenanceOutput(BaseModel):
    """设备预测性维护智能体标准输出"""

    summary: str = Field(..., description="分析摘要")
    decision: AgentDecision = Field(..., description="智能体决策")
    evidence: list[str] = Field(default_factory=list, description="支撑证据")
    next_actions: list[str] = Field(default_factory=list, description="建议后续行动")
    node_feedback: list[MaintenanceNodeFeedback] = Field(
        default_factory=list, description="节点式过程反馈"
    )
    sensor_evaluations: list[SensorEvaluationResult] = Field(default_factory=list)
    trend_analyses: list[TrendAnalysisResult] = Field(default_factory=list)
    risk_assessment: RiskAssessment | None = None
    failure_prediction: FailurePrediction | None = None
    time_window: TimeWindowEstimate | None = None
    work_order: WorkOrderSuggestion | None = None
