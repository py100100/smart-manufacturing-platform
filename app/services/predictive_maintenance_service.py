from __future__ import annotations

from app.schemas.predictive_maintenance import (
    EquipmentInfo,
    FailurePrediction,
    HistoricalFailure,
    MaintenanceContext,
    MaintenanceRule,
    RiskAssessment,
    RiskLevel,
    SensorEvaluationResult,
    SensorReading,
    SensorStatus,
    TimeWindowEstimate,
    TrendAnalysisResult,
    TrendDirection,
    WorkOrderSuggestion,
)

# ── 传感器阈值映射 ──────────────────────────────────────────────

SENSOR_RISK_VALUE: dict[SensorStatus, float] = {
    "normal": 0.0,
    "warning": 0.5,
    "critical": 1.0,
}

# ── 风险等级阈值 ────────────────────────────────────────────────

RISK_LEVEL_THRESHOLDS: list[tuple[float, RiskLevel]] = [
    (0.8, "critical"),
    (0.5, "high"),
    (0.25, "medium"),
]

# ── 故障时间窗口映射（基于风险等级） ────────────────────────────

RISK_TIME_WINDOW: dict[RiskLevel, tuple[float, str]] = {
    "critical": (24.0, "24 小时内"),
    "high": (72.0, "72 小时内"),
    "medium": (168.0, "168 小时内"),
    "low": (None, "无明确故障窗口"),
}

# ── 传感器异常 → 症状关键词 ─────────────────────────────────────

SENSOR_TO_SYMPTOM: dict[str, dict[SensorStatus, str]] = {
    "vibration": {"warning": "high_vibration", "critical": "high_vibration"},
    "temperature": {"warning": "temperature_rise", "critical": "temperature_rise"},
    "current": {"warning": "abnormal_current", "critical": "abnormal_current"},
    "pressure": {"warning": "abnormal_pressure", "critical": "abnormal_pressure"},
    "noise": {"warning": "abnormal_noise", "critical": "abnormal_noise"},
}

# ── 故障类型规则推断映射 ────────────────────────────────────────

RULE_BASED_FAILURE: dict[str, tuple[str, str, str]] = {
    # sensor_type → (failure_type, root_cause, recommended_action)
    "vibration": (
        "bearing_wear_or_spindle_fault",
        "高振动推测为轴承磨损、主轴异常或对中不良",
        "检查轴承状态、主轴对中情况及转子动平衡。",
    ),
    "temperature": (
        "cooling_or_lubrication_fault",
        "高温推测为冷却不足、润滑异常或负载过高",
        "检查冷却系统、润滑系统及负载工况。",
    ),
    "current": (
        "motor_or_electrical_fault",
        "电流异常推测为电机过载或电气故障",
        "检查电机负载、电气接线及驱动参数。",
    ),
    "pressure": (
        "hydraulic_or_pneumatic_fault",
        "压力异常推测为液压/气动系统异常",
        "检查液压/气动管路、密封件及泵站状态。",
    ),
    "noise": (
        "mechanical_wear_or_looseness",
        "噪声异常推测为机械磨损或结构松动",
        "检查紧固件、传动部件及防护罩状态。",
    ),
}


# ══════════════════════════════════════════════════════════════════
# PredictiveMaintenanceService
# ══════════════════════════════════════════════════════════════════


class PredictiveMaintenanceService:
    """设备预测性维护核心业务服务。

    职责：
    - 传感器阈值判断
    - 趋势异常分析
    - 故障风险评分
    - 历史故障匹配
    - 维护规程匹配
    - 预计故障时间窗口推断
    - 维护工单建议生成

    不直接访问数据库、不直接调用模型客户端。
    """

    # ── RAG 预留接口 ──────────────────────────────────────────

    @staticmethod
    def match_historical_failure(
        equipment_type: str,
        symptoms: list[str],
        historical_failures: list[HistoricalFailure],
    ) -> HistoricalFailure | None:
        """根据设备类型 + 症状匹配历史故障。

        **当前实现**：精确匹配 equipment_type，且 symptoms
        与历史记录的 symptoms 列表有交集（至少一个共同关键词）。
        **RAG 扩展预留**：未来可替换为 embedding 语义检索，
        支持跨设备类型模糊匹配，并返回匹配证据与置信度。
        """
        if not symptoms:
            return None
        symptoms_set = {s.lower() for s in symptoms}
        for hf in historical_failures:
            if hf.equipment_type != equipment_type:
                continue
            hf_symptoms = {s.lower() for s in hf.symptoms}
            if symptoms_set & hf_symptoms:
                return hf
        return None

    @staticmethod
    def match_maintenance_rule(
        equipment_type: str,
        failure_type: str,
        risk_level: RiskLevel,
        maintenance_rules: list[MaintenanceRule],
    ) -> MaintenanceRule | None:
        """根据设备类型 + 故障类型 + 风险等级匹配维护规程。

        **当前实现**：精确匹配三个字段。
        **RAG 扩展预留**：未来可替换为向量检索，
        支持模糊匹配相似设备/故障的维护规程推荐。
        """
        for rule in maintenance_rules:
            if (
                rule.equipment_type == equipment_type
                and rule.failure_type == failure_type
                and rule.risk_level == risk_level
            ):
                return rule
        # 降级：忽略 risk_level 再匹配
        for rule in maintenance_rules:
            if (
                rule.equipment_type == equipment_type
                and rule.failure_type == failure_type
            ):
                return rule
        return None

    # ── 传感器状态判断 ────────────────────────────────────────

    @staticmethod
    def evaluate_sensor(sensor: SensorReading) -> SensorEvaluationResult:
        """判断单个传感器状态。

        value >= threshold_critical → critical
        value >= threshold_warning → warning
        否则 → normal
        无阈值时默认 normal，不阻断流程。
        """
        status: SensorStatus = "normal"
        risk_value = 0.0

        if sensor.threshold_critical is not None and sensor.value >= sensor.threshold_critical:
            status = "critical"
            risk_value = 1.0
        elif sensor.threshold_warning is not None and sensor.value >= sensor.threshold_warning:
            status = "warning"
            risk_value = 0.5

        return SensorEvaluationResult(
            sensor_id=sensor.sensor_id,
            sensor_type=sensor.sensor_type,
            value=sensor.value,
            unit=sensor.unit,
            status=status,
            risk_value=risk_value,
            threshold_warning=sensor.threshold_warning,
            threshold_critical=sensor.threshold_critical,
        )

    @staticmethod
    def evaluate_all_sensors(
        sensors: list[SensorReading],
    ) -> list[SensorEvaluationResult]:
        """批量评估所有传感器。"""
        return [
            PredictiveMaintenanceService.evaluate_sensor(s)
            for s in sensors
        ]

    # ── 风险评分 ──────────────────────────────────────────────

    @staticmethod
    def assess_risk(
        evaluations: list[SensorEvaluationResult],
        equipment: EquipmentInfo,
    ) -> RiskAssessment:
        """综合风险评估。

        risk_score = 所有传感器风险值均值。
        设备处于 stopped/offline/maintenance 时在 evidence 注明，
        不直接按运行异常判断，风险值照常计算但会附加说明。
        """
        if not evaluations:
            return RiskAssessment()

        risk_values = [e.risk_value for e in evaluations]
        risk_score = sum(risk_values) / len(risk_values)

        # 确定风险等级
        risk_level: RiskLevel = "low"
        for threshold, level in RISK_LEVEL_THRESHOLDS:
            if risk_score >= threshold:
                risk_level = level
                break

        critical_sensors = [e.sensor_id for e in evaluations if e.status == "critical"]
        warning_sensors = [
            e.sensor_id for e in evaluations
            if e.status == "warning"
        ]

        return RiskAssessment(
            risk_score=round(risk_score, 4),
            risk_level=risk_level,
            critical_sensors=critical_sensors,
            warning_sensors=warning_sensors,
        )

    # ── 趋势分析 ──────────────────────────────────────────────

    @staticmethod
    def analyze_trends(
        sensor_readings: list[SensorReading],
        rise_threshold_pct: float = 20.0,
    ) -> list[TrendAnalysisResult]:
        """按 sensor_type 分组进行趋势分析。

        同一 sensor_type 有 >= 2 个时间点数据时：
        - 最近值 > 最早值 且增长 > rise_threshold_pct% → rising_trend
        - 最近值 < 最早值 且下降 > rise_threshold_pct% → falling_trend
        - 否则 → stable
        """
        # 按 sensor_type 分组
        groups: dict[str, list[SensorReading]] = {}
        for sr in sensor_readings:
            st = sr.sensor_type
            if st not in groups:
                groups[st] = []
            groups[st].append(sr)

        results: list[TrendAnalysisResult] = []

        for sensor_type, readings in groups.items():
            if len(readings) < 2:
                # 单数据点 → stable
                first = readings[0]
                results.append(
                    TrendAnalysisResult(
                        sensor_type=sensor_type,
                        direction="stable",
                        change_pct=0.0,
                        earliest_value=first.value,
                        latest_value=first.value,
                        data_points=1,
                        alert=False,
                    )
                )
                continue

            # 按时间戳排序（无时间戳则保持原序）
            sorted_readings = sorted(
                readings,
                key=lambda r: (
                    r.timestamp if isinstance(r.timestamp, str)
                    else r.timestamp.isoformat() if r.timestamp
                    else ""
                ),
            )

            earliest = sorted_readings[0].value
            latest = sorted_readings[-1].value
            data_points = len(sorted_readings)

            direction: TrendDirection = "stable"
            alert = False

            if earliest != 0 and latest != 0:
                if latest > earliest:
                    change_pct = (latest - earliest) / abs(earliest) * 100
                    if change_pct > rise_threshold_pct:
                        direction = "rising_trend"
                        alert = True
                else:
                    change_pct = (earliest - latest) / abs(earliest) * 100
                    if change_pct > rise_threshold_pct:
                        direction = "falling_trend"
                        alert = True
                if direction == "stable":
                    change_pct = (latest - earliest) / abs(earliest) * 100 if earliest != 0 else 0.0
            else:
                change_pct = 0.0
                if latest != earliest:
                    change_pct = 100.0
                    direction = "rising_trend" if latest > earliest else "falling_trend"
                    alert = True

            results.append(
                TrendAnalysisResult(
                    sensor_type=sensor_type,
                    direction=direction,
                    change_pct=round(change_pct, 2),
                    earliest_value=earliest,
                    latest_value=latest,
                    data_points=data_points,
                    alert=alert,
                )
            )

        return results

    # ── 故障症状生成 ──────────────────────────────────────────

    @staticmethod
    def generate_symptoms(
        evaluations: list[SensorEvaluationResult],
    ) -> list[str]:
        """从传感器评估结果生成症状关键词列表。"""
        symptoms: list[str] = []
        seen: set[str] = set()
        for ev in evaluations:
            if ev.status in ("warning", "critical"):
                sensor_map = SENSOR_TO_SYMPTOM.get(ev.sensor_type, {})
                symptom = sensor_map.get(ev.status, "")
                if symptom and symptom not in seen:
                    symptoms.append(symptom)
                    seen.add(symptom)
        return symptoms

    # ── 故障类型预测 ──────────────────────────────────────────

    @staticmethod
    def predict_failure(
        equipment_type: str,
        evaluations: list[SensorEvaluationResult],
        historical_failures: list[HistoricalFailure],
    ) -> FailurePrediction:
        """预测故障类型。

        优先匹配历史故障（equipment_type + symptoms）。
        无历史匹配时，按异常传感器类型做规则推断。
        """
        symptoms = PredictiveMaintenanceService.generate_symptoms(evaluations)

        # 无异常传感器
        if not symptoms:
            return FailurePrediction(
                failure_type="no_failure_detected",
                root_cause="所有传感器正常，未检测到故障迹象。",
                confidence=1.0,
                matched_symptoms=[],
                match_source="none",
            )

        # 优先：历史故障匹配
        matched = PredictiveMaintenanceService.match_historical_failure(
            equipment_type, symptoms, historical_failures
        )
        if matched is not None:
            return FailurePrediction(
                failure_type=matched.failure_type,
                root_cause=matched.root_cause,
                confidence=0.85,
                matched_symptoms=[s for s in symptoms if s.lower() in {
                    x.lower() for x in matched.symptoms
                }],
                mean_time_to_failure_hours=matched.mean_time_to_failure_hours,
                recommended_action=matched.recommended_action,
                match_source="historical",
            )

        # 次级：规则推断 —— 取 severity 最高（risk_value 最大）的异常传感器
        anomalous = sorted(
            [e for e in evaluations if e.status in ("warning", "critical")],
            key=lambda e: e.risk_value,
            reverse=True,
        )

        if anomalous:
            top = anomalous[0]
            rule = RULE_BASED_FAILURE.get(top.sensor_type)
            if rule:
                failure_type, root_cause, action = rule
                return FailurePrediction(
                    failure_type=failure_type,
                    root_cause=root_cause,
                    confidence=0.60,
                    matched_symptoms=symptoms,
                    recommended_action=action,
                    match_source="rule_based",
                )

        return FailurePrediction(
            failure_type="unknown_failure",
            root_cause="无法通过当前规则和症状明确推断故障类型。",
            confidence=0.0,
            matched_symptoms=symptoms,
            match_source="none",
        )

    # ── 故障时间窗口推断 ──────────────────────────────────────

    @staticmethod
    def estimate_time_window(
        risk_level: RiskLevel,
        failure_prediction: FailurePrediction,
    ) -> TimeWindowEstimate:
        """推断预计故障时间窗口。

        critical risk → 24 小时
        high risk → 72 小时
        medium risk → 168 小时
        low risk → 无明确窗口

        如果历史故障存在 mean_time_to_failure_hours，优先使用。
        """
        # 历史数据优先
        if (
            failure_prediction.match_source == "historical"
            and failure_prediction.mean_time_to_failure_hours is not None
            and failure_prediction.mean_time_to_failure_hours > 0
        ):
            hours = failure_prediction.mean_time_to_failure_hours
            return TimeWindowEstimate(
                estimated_window_hours=hours,
                window_description=f"基于历史数据，预计 {hours:.0f} 小时内可能发生故障",
                source="historical",
            )

        window_hours, description = RISK_TIME_WINDOW.get(
            risk_level, (None, "无明确故障窗口")
        )

        if window_hours is not None:
            return TimeWindowEstimate(
                estimated_window_hours=window_hours,
                window_description=f"基于风险等级 {risk_level}，预计 {description}",
                source="risk_based",
            )

        return TimeWindowEstimate(
            estimated_window_hours=None,
            window_description="当前风险等级低，无明确故障时间窗口。",
            source="none",
        )

    # ── 维护工单建议生成 ──────────────────────────────────────

    @staticmethod
    def generate_work_order(
        equipment: EquipmentInfo,
        risk_assessment: RiskAssessment,
        failure_prediction: FailurePrediction,
        time_window: TimeWindowEstimate,
        maintenance_rules: list[MaintenanceRule],
        decision: str,
        context: "MaintenanceContext | None" = None,
    ) -> WorkOrderSuggestion | None:
        """生成维护工单建议。

        满足以下任一条件时生成：
        - risk_level == critical
        - risk_level == high
        - decision == maintenance_work_order_required

        维护动作优先级：rule.maintenance_action
        > rule.procedure_steps > failure_prediction.recommended_action
        """
        should_generate = (
            risk_assessment.risk_level == "critical"
            or risk_assessment.risk_level == "high"
            or decision == "maintenance_work_order_required"
        )

        if not should_generate:
            return None

        # 匹配维护规程
        rule = PredictiveMaintenanceService.match_maintenance_rule(
            equipment.equipment_type,
            failure_prediction.failure_type,
            risk_assessment.risk_level,
            maintenance_rules,
        )

        work_order_type = "corrective"
        priority = "medium"
        required_parts: list[str] = []
        estimated_hours = 4.0
        procedure_action = failure_prediction.recommended_action

        if rule is not None:
            work_order_type = rule.work_order_type
            priority = rule.priority
            required_parts = list(rule.required_parts)
            estimated_hours = rule.estimated_duration_hours
            # 优先级：maintenance_action > procedure_steps > failure_prediction.recommended_action
            if rule.maintenance_action:
                procedure_action = rule.maintenance_action
            elif rule.procedure_steps:
                procedure_action = "；".join(rule.procedure_steps)

        # 确定紧急程度
        if risk_assessment.risk_level == "critical":
            priority = "critical"
        elif risk_assessment.risk_level == "high":
            if priority not in ("critical",):
                priority = "high"

        # context 驱动：生产关键性提升说明但不硬改风险分
        reason_parts: list[str] = [
            f"设备 {equipment.equipment_id} 风险等级 {risk_assessment.risk_level}，"
            f"风险评分 {risk_assessment.risk_score:.2f}，"
            f"故障类型 {failure_prediction.failure_type}",
        ]
        if context is not None:
            if context.production_criticality in ("critical", "high"):
                reason_parts.append(
                    f"生产关键性: {context.production_criticality}，"
                    "建议优先安排维护窗口"
                )
            if not context.spare_parts_available:
                reason_parts.append(
                    "备件不可用，请提前协调采购或调用替代件"
                )
            if (
                context.maintenance_window_hours is not None
                and context.maintenance_window_hours < estimated_hours
            ):
                reason_parts.append(
                    f"维护窗口 ({context.maintenance_window_hours:.1f}h) "
                    f"小于预计工时 ({estimated_hours:.1f}h)，"
                    "需协调延长时间或拆分作业"
                )

        return WorkOrderSuggestion(
            work_order_type=work_order_type,
            equipment_id=equipment.equipment_id,
            failure_type=failure_prediction.failure_type,
            priority=priority,
            recommended_action=procedure_action,
            required_parts=required_parts,
            estimated_duration_hours=estimated_hours,
            suggested_start_window=time_window.window_description,
            reason="；".join(reason_parts),
        )
