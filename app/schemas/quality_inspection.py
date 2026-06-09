from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

# ── 缺陷严重度枚举 ──────────────────────────────────────────────

DefectSeverity = Literal["critical", "major", "minor"]

# ── 根因类别枚举 ────────────────────────────────────────────────

RootCauseCategory = Literal["man", "machine", "material", "method", "environment", "unknown"]

# ── 智能体决策枚举 ──────────────────────────────────────────────

AgentDecision = Literal[
    "quality_passed",
    "quality_risk_detected",
    "defect_pattern_detected",
    "critical_quality_issue",
    "root_cause_identified",
    "standard_missing",
]

# ── 节点状态枚举 ──────────────────────────────────────────────────

NodeResultStatus = Literal["success", "warning", "failed"]


# ══════════════════════════════════════════════════════════════════
# 输入数据结构
# ══════════════════════════════════════════════════════════════════


class InspectionBatch(BaseModel):
    """质检批次信息"""

    batch_id: str = Field(..., description="批次编号，如 BATCH-001")
    product_id: str = Field(..., description="产品编号，如 P-1001")
    process_step: str = Field(..., description="工序名称，如 CNC machining")
    inspection_time: datetime | str = Field(..., description="检验时间")
    inspector_id: str = Field(default="", description="检验员编号")


class InspectionItem(BaseModel):
    """单项质检指标"""

    item_id: str = Field(..., description="检验项编号")
    metric_name: str = Field(..., description="指标名称，如 outer_diameter")
    measured_value: float = Field(..., description="实测值")
    standard_min: float | None = Field(default=None, description="标准下限")
    standard_max: float | None = Field(default=None, description="标准上限")
    unit: str = Field(default="", description="单位，如 mm")
    sample_no: str = Field(default="", description="样品编号")


class DefectRecord(BaseModel):
    """缺陷记录。

    字段 count 为任务书规定的主字段名，同时兼容 quantity 输入。
    """

    defect_id: str = Field(..., description="缺陷编号")
    defect_type: str = Field(..., description="缺陷类型，如 scratch, crack, size_deviation")
    severity: DefectSeverity = Field(default="minor", description="严重程度")
    location: str = Field(default="", description="缺陷位置，如 surface, edge")
    item_id: str = Field(default="", description="关联的检验项编号")
    description: str = Field(default="", description="缺陷描述")
    count: int = Field(
        default=1,
        ge=1,
        validation_alias=AliasChoices("count", "quantity"),
        description="该缺陷出现次数",
    )
    product_id: str = Field(default="", description="产品编号")
    process_step: str = Field(default="", description="工序")


class QualityStandard(BaseModel):
    """质量标准。standard_id 可选，未传时自动生成。"""

    standard_id: str = Field(default="", description="标准编号（可选）")
    product_id: str = Field(..., description="适用产品编号")
    metric_name: str = Field(..., description="指标名称")
    standard_min: float | None = Field(default=None, description="标准下限")
    standard_max: float | None = Field(default=None, description="标准上限")
    unit: str = Field(default="", description="单位")
    source: str = Field(default="", description="标准来源，如 GB/T 1184-1996")


class HistoricalDefect(BaseModel):
    """历史缺陷记录。record_id 可选，未传时自动生成。"""

    record_id: str = Field(default="", description="记录编号（可选）")
    product_id: str = Field(..., description="产品编号")
    process_step: str = Field(..., description="工序")
    defect_type: str = Field(..., description="缺陷类型")
    root_cause_category: RootCauseCategory = Field(default="unknown", description="根因类别")
    root_cause: str = Field(default="", description="根因描述")
    corrective_action: str = Field(default="", description="纠正措施")
    occurrence_count: int = Field(default=1, ge=0, description="历史发生次数")
    resolved: bool = Field(default=False, description="是否已解决")


# ══════════════════════════════════════════════════════════════════
# 现场上下文（人机料法环）
# ══════════════════════════════════════════════════════════════════


class InspectionContext(BaseModel):
    """检验现场上下文 —— 支撑人机料法环根因追溯。

    每个字段均为可选；提供越完整，根因推断越准确。
    """

    operator_id: str = Field(default="", description="操作者/检验员编号")
    machine_id: str = Field(default="", description="设备/机台编号")
    material_batch_id: str = Field(default="", description="材料批次编号")
    environment: dict[str, float] = Field(
        default_factory=dict,
        description="环境参数（如 temperature、humidity 等）",
    )
    process_params: dict[str, float] = Field(
        default_factory=dict,
        description="工艺参数（如 cutting_speed、feed_rate、temperature_setpoint 等）",
    )


# ══════════════════════════════════════════════════════════════════
# 智能体请求
# ══════════════════════════════════════════════════════════════════


class QualityInspectionRequest(BaseModel):
    """质量检测与缺陷分析智能体入参。

    任务书原始样例可直接构造。
    """

    inspection_batch: InspectionBatch = Field(..., description="质检批次信息")
    inspection_items: list[InspectionItem] = Field(
        default_factory=list, description="质检指标列表"
    )
    defect_records: list[DefectRecord] = Field(
        default_factory=list, description="缺陷记录列表"
    )
    quality_standards: list[QualityStandard] = Field(
        default_factory=list,
        description="质量标准列表（可选，优先于 inspection_items 内置标准）",
    )
    historical_defects: list[HistoricalDefect] = Field(
        default_factory=list,
        description="历史缺陷记录（可选，用于根因匹配）",
    )
    context: InspectionContext | None = Field(
        default=None,
        description=(
            "现场上下文（operator_id / machine_id / material_batch_id / "
            "environment / process_params），用于人机料法环根因推断"
        ),
    )
    pattern_threshold: int = Field(
        default=10, ge=1, description="缺陷模式识别阈值：同一 defect_type 出现 >= 该值时视为模式"
    )
    # 保留兼容旧调用方，但优先使用 context.environment
    environment_data: dict[str, float] = Field(
        default_factory=dict,
        description="【已废弃】环境数据，建议改用 context.environment",
    )


# ══════════════════════════════════════════════════════════════════
# 输出数据结构
# ══════════════════════════════════════════════════════════════════


class QualityIndicatorResult(BaseModel):
    """单个质检指标判定结果"""

    item_id: str
    metric_name: str
    measured_value: float
    standard_min: float | None = None
    standard_max: float | None = None
    unit: str = ""
    passed: bool
    deviation: float = 0.0
    standard_source: str = ""  # "quality_standards" | "inspection_items" | "none"
    note: str = ""


class DefectClassificationResult(BaseModel):
    """缺陷分类结果"""

    total_defects: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_location: dict[str, int] = Field(default_factory=dict)
    critical_items: list[str] = Field(default_factory=list)
    top_defect_type: str = ""


class DefectPatternInfo(BaseModel):
    """缺陷模式信息"""

    pattern_detected: bool = False
    pattern_type: str = ""
    detail: str = ""
    high_frequency_types: list[str] = Field(default_factory=list)
    location_clusters: list[str] = Field(default_factory=list)
    total_defects_in_batch: int = 0


class RootCauseResult(BaseModel):
    """根因追溯结果"""

    root_cause_category: RootCauseCategory = "unknown"
    root_cause: str = ""
    confidence: float = 0.0
    matched_evidence: list[str] = Field(default_factory=list)
    corrective_action: str = ""
    match_source: str = ""  # "historical" | "rule_based" | "none"


class RecommendationItem(BaseModel):
    """改进建议条目"""

    priority: DefectSeverity = "minor"
    target: str = ""
    action: str = ""
    expected_effect: str = ""
    responsible_role: str = ""


# ══════════════════════════════════════════════════════════════════
# 节点反馈
# ══════════════════════════════════════════════════════════════════


class QualityNodeFeedback(BaseModel):
    """质量检测智能体单节点反馈。"""

    node: str = Field(..., description="节点标识")
    status: NodeResultStatus = Field(..., description="节点状态")
    message: str = Field(..., description="节点反馈信息")


# ══════════════════════════════════════════════════════════════════
# 智能体输出
# ══════════════════════════════════════════════════════════════════


class QualityInspectionAgentOutput(BaseModel):
    """质量检测与缺陷分析智能体标准输出"""

    summary: str = Field(..., description="分析摘要")
    decision: AgentDecision = Field(..., description="智能体决策")
    evidence: list[str] = Field(default_factory=list, description="支撑证据")
    next_actions: list[str] = Field(default_factory=list, description="建议后续行动")
    node_feedback: list[QualityNodeFeedback] = Field(
        default_factory=list, description="节点式过程反馈"
    )
    indicator_results: list[QualityIndicatorResult] = Field(default_factory=list)
    classification: DefectClassificationResult | None = None
    pattern_info: DefectPatternInfo | None = None
    root_cause_result: RootCauseResult | None = None
    recommendations: list[RecommendationItem] = Field(default_factory=list)
