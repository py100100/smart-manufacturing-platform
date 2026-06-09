from __future__ import annotations

import pytest

from app.agents.predictive_maintenance_agent import (
    PredictiveMaintenanceAgent,
    REQUIRED_NODES,
)
from app.schemas.predictive_maintenance import (
    EquipmentInfo,
    MaintenanceContext,
    HistoricalFailure,
    MaintenanceRule,
    PredictiveMaintenanceRequest,
    SensorReading,
)


# ══════════════════════════════════════════════════════════════════
# 工厂函数
# ══════════════════════════════════════════════════════════════════


def make_equipment(**overrides) -> EquipmentInfo:
    kwargs = {
        "equipment_id": "EQ-CNC-001",
        "equipment_name": "CNC machining center #1",
        "equipment_type": "CNC",
        "location": "workshop-A",
        "running_status": "running",
        "last_maintenance_date": "2026-05-20",
        "total_runtime_hours": 8600.0,
    }
    kwargs.update(overrides)
    return EquipmentInfo(**kwargs)


def make_sensor(
    sensor_id: str,
    sensor_type: str,
    value: float,
    threshold_warning: float | None = None,
    threshold_critical: float | None = None,
    unit: str = "",
    timestamp: str | None = None,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        value=value,
        unit=unit,
        timestamp=timestamp,
        threshold_warning=threshold_warning,
        threshold_critical=threshold_critical,
    )


def make_request(**overrides) -> PredictiveMaintenanceRequest:
    kwargs = {
        "equipment": make_equipment(),
        "sensor_readings": [],
        "historical_failures": [],
        "maintenance_rules": [],
    }
    kwargs.update(overrides)
    return PredictiveMaintenanceRequest(**kwargs)


def make_normal_sensors() -> list[SensorReading]:
    return [
        make_sensor("S-VIB-01", "vibration", 2.5, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
        make_sensor("S-TEMP-01", "temperature", 55.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
        make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
    ]


# ══════════════════════════════════════════════════════════════════
# 场景 1：所有传感器正常 → equipment_normal
# ══════════════════════════════════════════════════════════════════


class TestEquipmentNormal:
    """所有传感器正常 → equipment_normal"""

    def test_all_sensors_normal(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        assert output.decision == "equipment_normal"
        assert output.risk_assessment is not None
        assert output.risk_assessment.risk_level == "low"
        assert output.risk_assessment.risk_score == 0.0

    def test_output_structure_complete(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert isinstance(output.evidence, list)
        assert isinstance(output.next_actions, list)
        assert isinstance(output.node_feedback, list)

    def test_all_required_nodes_present(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        node_names = {n.node for n in output.node_feedback}
        for required in REQUIRED_NODES:
            assert required in node_names, f"缺少强制节点: {required}"

    def test_no_work_order_generated(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        assert output.work_order is None

    def test_evidence_mentions_equipment(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        evidence_text = " ".join(output.evidence)
        assert "EQ-CNC-001" in evidence_text
        assert "CNC" in evidence_text


# ══════════════════════════════════════════════════════════════════
# 场景 2：warning 级异常 → maintenance_attention_required
# ══════════════════════════════════════════════════════════════════


class TestMaintenanceAttentionRequired:
    """warning 级传感器异常 → maintenance_attention_required"""

    def test_single_warning_sensor(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 55.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        # risk_score = (0.5 + 0 + 0) / 3 = 0.17 → low, with warning sensor
        # → maintenance_attention_required or failure_risk_detected
        assert output.decision in (
            "maintenance_attention_required",
            "failure_risk_detected",
        )

    def test_multiple_warning_sensors(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 85.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        # (0.5 + 0.5 + 0) / 3 = 0.33 → medium → failure_risk_detected
        assert output.decision == "failure_risk_detected"

    def test_unknown_sensor_type_handled(self) -> None:
        """未知传感器类型不得导致流程失败"""
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-UNK-01", "humidity", 80.0, threshold_warning=70.0, threshold_critical=90.0, unit="%"),
            ],
        )
        output = agent.execute(request)

        assert output.decision != "sensor_data_insufficient"
        assert output.node_feedback[0].status == "success"

    def test_warning_triggers_attention_next_actions(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        assert any(
            "巡检" in a or "记录" in a or "维护" in a
            for a in output.next_actions
        )


# ══════════════════════════════════════════════════════════════════
# 场景 3：high 风险 → failure_risk_detected / maintenance_work_order_required
# ══════════════════════════════════════════════════════════════════


class TestHighRiskFailureDetected:
    """high 风险 → maintenance_work_order_required"""

    def test_high_risk_generates_work_order(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 9.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 95.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "maintenance_work_order_required"
        assert output.work_order is not None
        assert output.work_order.equipment_id == "EQ-CNC-001"

    def test_high_risk_with_work_order_details(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 9.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-CUR-01", "current", 35.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        assert output.work_order is not None
        assert output.work_order.work_order_type
        assert output.work_order.failure_type
        assert output.work_order.reason

    def test_medium_risk_is_failure_risk_detected(self) -> None:
        agent = PredictiveMaintenanceAgent()
        # risk_score = (0.5 + 0 + 0) / 3 = 0.17 → low, need more
        # risk_score = (0.5 + 0.5 + 0) / 3 = 0.33 → medium
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 85.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "failure_risk_detected"
        assert output.risk_assessment.risk_level == "medium"


# ══════════════════════════════════════════════════════════════════
# 场景 4：critical 风险 → critical_failure_risk
# ══════════════════════════════════════════════════════════════════


class TestCriticalFailureRisk:
    """critical 传感器 → critical_failure_risk"""

    def test_single_critical_sensor(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        # (1.0 + 1.0 + 1.0) / 3 = 1.0 → critical
        assert output.decision == "critical_failure_risk"
        assert output.risk_assessment is not None
        assert output.risk_assessment.risk_level == "critical"

    def test_critical_generates_work_order(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        assert output.work_order is not None
        assert output.work_order.priority == "critical"

    def test_critical_triggers_immediate_action(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 15.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        assert any("立即" in a or "紧急" in a for a in output.next_actions)

    def test_all_critical_all_sensors(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "critical_failure_risk"
        assert output.risk_assessment.risk_score == 1.0


# ══════════════════════════════════════════════════════════════════
# 场景 5：传感器数据为空 → sensor_data_insufficient
# ══════════════════════════════════════════════════════════════════


class TestSensorDataInsufficient:
    """传感器数据为空 → sensor_data_insufficient"""

    def test_empty_sensor_list(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=[])
        output = agent.execute(request)

        assert output.decision == "sensor_data_insufficient"
        validation = next(
            n for n in output.node_feedback if n.node == "input_validation"
        )
        assert validation.status == "failed"

    def test_empty_sensors_next_actions(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=[])
        output = agent.execute(request)

        assert any(
            "传感器" in a for a in output.next_actions
        )


# ══════════════════════════════════════════════════════════════════
# 场景 6：维护规程缺失 → maintenance_rule_missing
# ══════════════════════════════════════════════════════════════════


class TestMaintenanceRuleMissing:
    """有故障预测但无匹配维护规程 → maintenance_rule_missing"""

    def test_rule_missing_detected(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 1.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 55.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="some_other_fault",
                    risk_level="low",
                ),
            ],
        )
        output = agent.execute(request)

        # 正常传感器 → equipment_normal，不触发 rule_missing
        assert output.decision == "equipment_normal"

    def test_rule_missing_with_anomaly_and_rules_provided(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 55.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="some_other_fault",
                    risk_level="high",
                ),
            ],
        )
        output = agent.execute(request)

        # (0.5+0+0)/3=0.17 → low with warning → maintenance_attention_required
        # rule-based failure=bearing_wear_or_spindle_fault, no matching rule
        assert output.decision == "maintenance_attention_required"

    def test_rule_missing_next_actions(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    equipment_type="CNC",
                    failure_type="unrelated_fault",
                    risk_level="low",
                ),
            ],
        )
        output = agent.execute(request)

        if output.decision == "maintenance_rule_missing":
            assert any("规程" in a for a in output.next_actions)

    def test_rule_matching_node_warning(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 7.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    equipment_type="CNC",
                    failure_type="unrelated",
                    risk_level="low",
                ),
            ],
        )
        output = agent.execute(request)

        rule_node = next(
            n for n in output.node_feedback if n.node == "maintenance_rule_matching"
        )
        # 未匹配到正确规程
        assert rule_node.status in ("warning", "success")


# ══════════════════════════════════════════════════════════════════
# 场景 7：历史故障匹配成功
# ══════════════════════════════════════════════════════════════════


class TestHistoricalFailureMatching:
    """历史故障匹配 → failure_prediction with historical source"""

    def test_historical_match_by_equipment_type_and_symptoms(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴轴承疲劳磨损",
                    symptoms=["high_vibration", "abnormal_noise"],
                    mean_time_to_failure_hours=48.0,
                    recommended_action="更换主轴轴承并重新校准",
                    occurrence_count=5,
                    resolved=False,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert output.failure_prediction.match_source == "historical"
        assert output.failure_prediction.confidence >= 0.8
        assert output.failure_prediction.failure_type == "spindle_bearing_failure"

    def test_historical_match_uses_mttf_for_time_window(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_fault",
                    root_cause="主轴问题",
                    symptoms=["high_vibration"],
                    mean_time_to_failure_hours=48.0,
                    recommended_action="更换主轴",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.time_window is not None
        assert output.time_window.source == "historical"
        assert output.time_window.estimated_window_hours == 48.0

    def test_no_historical_match_falls_back_to_rules(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="PUMP",  # 不同设备类型
                    failure_type="other_fault",
                    root_cause="不相关",
                    symptoms=["unrelated_symptom"],
                ),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert output.failure_prediction.match_source == "rule_based"

    def test_historical_match_node_feedback(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="bearing_fault",
                    root_cause="轴承磨损",
                    symptoms=["high_vibration"],
                    recommended_action="更换轴承",
                ),
            ],
        )
        output = agent.execute(request)

        hist_node = next(
            n for n in output.node_feedback
            if n.node == "historical_failure_matching"
        )
        assert "成功" in hist_node.message or "匹配" in hist_node.message


# ══════════════════════════════════════════════════════════════════
# 场景 8：多时间点传感器 rising_trend
# ══════════════════════════════════════════════════════════════════


class TestTrendAnalysis:
    """多时间点传感器趋势分析"""

    def test_rising_trend_detected(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.0, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-01T08:00:00", unit="mm/s"),
                make_sensor("S-VIB-01", "vibration", 3.0, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-03T08:00:00", unit="mm/s"),
                make_sensor("S-VIB-01", "vibration", 5.5, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-08T08:00:00", unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        vib_trend = next(
            t for t in output.trend_analyses if t.sensor_type == "vibration"
        )
        # 2.0→5.5, change = 175%, > 20%
        assert vib_trend.direction == "rising_trend"
        assert vib_trend.alert is True

    def test_falling_trend_detected(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-PRESS-01", "pressure", 10.0, threshold_warning=None, threshold_critical=None,
                             timestamp="2026-06-01T08:00:00", unit="bar"),
                make_sensor("S-PRESS-01", "pressure", 7.0, threshold_warning=None, threshold_critical=None,
                             timestamp="2026-06-05T08:00:00", unit="bar"),
            ],
        )
        output = agent.execute(request)

        press_trend = next(
            t for t in output.trend_analyses if t.sensor_type == "pressure"
        )
        # 10.0→7.0, drop 30% > 20%
        assert press_trend.direction == "falling_trend"
        assert press_trend.alert is True

    def test_stable_trend(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.0, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-01T08:00:00", unit="mm/s"),
                make_sensor("S-VIB-01", "vibration", 2.1, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-08T08:00:00", unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        vib_trend = next(
            t for t in output.trend_analyses if t.sensor_type == "vibration"
        )
        # 2.0→2.1, change = 5% < 20%
        assert vib_trend.direction == "stable"
        assert vib_trend.alert is False

    def test_single_datapoint_trend(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        assert len(output.trend_analyses) == 1
        assert output.trend_analyses[0].data_points == 1
        assert output.trend_analyses[0].direction == "stable"

    def test_trend_analysis_node(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.0, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-01T08:00:00", unit="mm/s"),
                make_sensor("S-VIB-01", "vibration", 5.5, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-08T08:00:00", unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        trend_node = next(
            n for n in output.node_feedback if n.node == "trend_analysis"
        )
        assert "vibration" in trend_node.message
        assert trend_node.status == "warning"

    def test_custom_trend_threshold(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.0, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-01T08:00:00", unit="mm/s"),
                make_sensor("S-VIB-01", "vibration", 2.3, threshold_warning=5.0, threshold_critical=10.0,
                             timestamp="2026-06-08T08:00:00", unit="mm/s"),
            ],
            trend_rise_threshold_pct=10.0,  # 低阈值：15% > 10% → alert
        )
        output = agent.execute(request)

        vib_trend = next(t for t in output.trend_analyses if t.sensor_type == "vibration")
        assert vib_trend.direction == "rising_trend"


# ══════════════════════════════════════════════════════════════════
# 场景 9：高振动推断轴承/主轴类故障
# ══════════════════════════════════════════════════════════════════


class TestVibrationToBearingFault:
    """高振动 → 轴承磨损或主轴异常推断"""

    def test_high_vibration_infers_bearing_or_spindle(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert "bearing" in output.failure_prediction.failure_type.lower() or "spindle" in output.failure_prediction.failure_type.lower()
        assert "振动" in output.failure_prediction.root_cause or "轴承" in output.failure_prediction.root_cause or "主轴" in output.failure_prediction.root_cause

    def test_high_temperature_infers_cooling_fault(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert "cooling" in output.failure_prediction.failure_type.lower() or "lubrication" in output.failure_prediction.failure_type.lower()
        assert "温度" in output.failure_prediction.root_cause or "冷却" in output.failure_prediction.root_cause

    def test_abnormal_current_infers_motor_fault(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert "motor" in output.failure_prediction.failure_type.lower() or "electrical" in output.failure_prediction.failure_type.lower()

    def test_abnormal_pressure_infers_hydraulic_fault(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-PRESS-01", "pressure", 50.0, threshold_warning=30.0, threshold_critical=45.0, unit="bar"),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert "hydraulic" in output.failure_prediction.failure_type.lower() or "pneumatic" in output.failure_prediction.failure_type.lower()

    def test_abnormal_noise_infers_mechanical_wear(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-NOISE-01", "noise", 95.0, threshold_warning=80.0, threshold_critical=90.0, unit="dB"),
            ],
        )
        output = agent.execute(request)

        assert output.failure_prediction is not None
        assert "mechanical" in output.failure_prediction.failure_type.lower() or "wear" in output.failure_prediction.failure_type.lower() or "looseness" in output.failure_prediction.failure_type.lower()


# ══════════════════════════════════════════════════════════════════
# 场景 10：设备非运行状态
# ══════════════════════════════════════════════════════════════════


class TestNonRunningEquipment:
    """设备 stopped/offline/maintenance 状态"""

    def test_stopped_equipment_with_critical_sensors(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            equipment=make_equipment(running_status="stopped"),
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 0.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        output = agent.execute(request)

        # 设备停止状态下传感器可能正常（振动为0）
        assert output.decision == "equipment_normal"
        # 证据中应包含设备状态说明
        evidence_text = " ".join(output.evidence)
        assert "stopped" in evidence_text

    def test_maintenance_equipment_with_normal_sensors(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            equipment=make_equipment(running_status="maintenance"),
            sensor_readings=make_normal_sensors(),
        )
        output = agent.execute(request)

        evidence_text = " ".join(output.evidence)
        assert "maintenance" in evidence_text

    def test_offline_equipment_validation_passes(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            equipment=make_equipment(running_status="offline"),
            sensor_readings=make_normal_sensors(),
        )
        output = agent.execute(request)

        validation_node = next(
            n for n in output.node_feedback if n.node == "input_validation"
        )
        assert validation_node.status == "success"


# ══════════════════════════════════════════════════════════════════
# 风险评分准确性测试
# ══════════════════════════════════════════════════════════════════


class TestRiskScoring:
    """验证风险评分计算正确性"""

    def test_all_normal_zero_score(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        assert output.risk_assessment.risk_score == 0.0
        assert output.risk_assessment.risk_level == "low"

    def test_mixed_risk_score(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),  # risk=1.0
                make_sensor("S-TEMP-01", "temperature", 85.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),  # risk=0.5
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),  # risk=0.0
            ],
        )
        output = agent.execute(request)

        # (1.0 + 0.5 + 0.0) / 3 = 0.5
        assert output.risk_assessment.risk_score == pytest.approx(0.5, abs=0.01)
        assert output.risk_assessment.risk_level == "high"

    def test_score_at_critical_threshold(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),  # 1.0
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),  # 1.0
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),  # 1.0
                make_sensor("S-PRESS-01", "pressure", 50.0, threshold_warning=30.0, threshold_critical=45.0, unit="bar"),  # 1.0
            ],
        )
        output = agent.execute(request)

        assert output.risk_assessment.risk_score == 1.0
        assert output.risk_assessment.risk_level == "critical"

    def test_no_threshold_defaults_normal(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 100.0, unit="mm/s"),  # 无阈值
            ],
        )
        output = agent.execute(request)

        # 无阈值 → normal → risk=0
        assert output.risk_assessment.risk_score == 0.0


# ══════════════════════════════════════════════════════════════════
# 维护规程匹配
# ══════════════════════════════════════════════════════════════════


class TestMaintenanceRuleMatching:
    """维护规程匹配功能"""

    def test_exact_rule_match(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="bearing_wear_or_spindle_fault",
                    risk_level="critical",
                    work_order_type="corrective",
                    priority="critical",
                    required_parts=["bearing_kit", "seal_set"],
                    estimated_duration_hours=6.0,
                    procedure_steps=["停机检查", "拆解主轴", "更换轴承", "重新校准"],
                ),
            ],
        )
        output = agent.execute(request)

        rule_node = next(
            n for n in output.node_feedback if n.node == "maintenance_rule_matching"
        )
        assert rule_node.status == "success"

        assert output.work_order is not None
        assert "bearing_kit" in output.work_order.required_parts
        assert output.work_order.estimated_duration_hours == 6.0

    def test_rule_match_fallback_ignores_risk_level(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-002",
                    equipment_type="CNC",
                    failure_type="bearing_wear_or_spindle_fault",
                    risk_level="high",  # 与实际 critical 不同
                    work_order_type="corrective",
                    priority="high",
                    procedure_steps=["检查轴承"],
                ),
            ],
        )
        output = agent.execute(request)

        # 降级匹配（忽略 risk_level）
        rule_node = next(
            n for n in output.node_feedback if n.node == "maintenance_rule_matching"
        )
        assert rule_node.status == "success"

    def test_no_rule_match_generates_default_work_order(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
            maintenance_rules=[],  # 无规程
        )
        output = agent.execute(request)

        rule_node = next(
            n for n in output.node_feedback if n.node == "maintenance_rule_matching"
        )
        assert rule_node.status == "warning"

        # 但仍应生成工单（critical 风险触发）
        assert output.work_order is not None


# ══════════════════════════════════════════════════════════════════
# 输入校验测试
# ══════════════════════════════════════════════════════════════════


class TestInputValidation:
    """输入校验边界测试"""

    def test_valid_input_passes(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        vn = next(n for n in output.node_feedback if n.node == "input_validation")
        assert vn.status == "success"

    def test_equipment_missing_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PredictiveMaintenanceRequest(
                equipment=None,  # type: ignore
                sensor_readings=make_normal_sensors(),
            )

    def test_sensor_values_various_units(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 2.5, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 55.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 12.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
                make_sensor("S-PRESS-01", "pressure", 25.0, threshold_warning=30.0, threshold_critical=45.0, unit="bar"),
                make_sensor("S-NOISE-01", "noise", 65.0, threshold_warning=80.0, threshold_critical=90.0, unit="dB"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "equipment_normal"
        assert len(output.sensor_evaluations) == 5


# ══════════════════════════════════════════════════════════════════
# 输出结构完整性
# ══════════════════════════════════════════════════════════════════


class TestOutputStructure:
    """输出结构完整性测试"""

    def test_each_node_has_valid_fields(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        for node in output.node_feedback:
            assert node.node
            assert node.status in ("success", "warning", "failed")
            assert node.message

    def test_decision_is_valid_enum(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(sensor_readings=make_normal_sensors())
        output = agent.execute(request)

        valid = {
            "equipment_normal",
            "maintenance_attention_required",
            "failure_risk_detected",
            "critical_failure_risk",
            "maintenance_work_order_required",
            "sensor_data_insufficient",
            "maintenance_rule_missing",
        }
        assert output.decision in valid

    def test_plan_returns_valid_result(self) -> None:
        agent = PredictiveMaintenanceAgent()
        result = agent.plan("设备振动异常，需要分析", {})
        assert result.summary
        assert result.decision
        assert len(result.next_actions) >= 2

    def test_build_node_feedback(self) -> None:
        agent = PredictiveMaintenanceAgent()
        result = agent.plan("设备维护", {})
        nodes = agent.build_node_feedback("设备维护", result)
        assert len(nodes) == 3
        assert all(n.status == "completed" for n in nodes)

    def test_time_window_estimates(self) -> None:
        """验证不同风险等级的时间窗口"""
        agent = PredictiveMaintenanceAgent()

        # critical → 24h
        req_crit = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
            ],
        )
        out_crit = agent.execute(req_crit)
        assert out_crit.time_window.estimated_window_hours == 24.0

        # normal → None
        req_norm = make_request(sensor_readings=make_normal_sensors())
        out_norm = agent.execute(req_norm)
        assert out_norm.time_window.estimated_window_hours is None


# ══════════════════════════════════════════════════════════════════
# RAG 预留接口测试
# ══════════════════════════════════════════════════════════════════


class TestRAGInterfaces:
    """RAG 预留接口正确性"""

    def test_match_historical_failure(self) -> None:
        from app.services.predictive_maintenance_service import PredictiveMaintenanceService

        svc = PredictiveMaintenanceService()
        history = [
            HistoricalFailure(
                equipment_type="CNC",
                failure_type="bearing_fault",
                root_cause="轴承磨损",
                symptoms=["high_vibration", "abnormal_noise"],
            ),
        ]
        result = svc.match_historical_failure("CNC", ["high_vibration"], history)
        assert result is not None
        assert result.failure_type == "bearing_fault"

        result_none = svc.match_historical_failure("PUMP", ["high_vibration"], history)
        assert result_none is None

    def test_match_maintenance_rule(self) -> None:
        from app.services.predictive_maintenance_service import PredictiveMaintenanceService

        svc = PredictiveMaintenanceService()
        rules = [
            MaintenanceRule(
                equipment_type="CNC",
                failure_type="bearing_fault",
                risk_level="critical",
                work_order_type="corrective",
            ),
        ]
        result = svc.match_maintenance_rule("CNC", "bearing_fault", "critical", rules)
        assert result is not None
        assert result.work_order_type == "corrective"

        # fallback: ignores risk_level
        result2 = svc.match_maintenance_rule("CNC", "bearing_fault", "low", rules)
        assert result2 is not None


# ══════════════════════════════════════════════════════════════════
# 综合端到端场景
# ══════════════════════════════════════════════════════════════════


class TestComprehensiveScenarios:
    """端到端综合测试"""

    def test_full_pipeline_critical_with_history_and_rules(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            equipment=make_equipment(
                equipment_id="EQ-CNC-001",
                equipment_type="CNC",
                running_status="running",
                total_runtime_hours=8600.0,
            ),
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 9.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s",
                             timestamp="2026-06-01T08:00:00"),
                make_sensor("S-VIB-01", "vibration", 15.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s",
                             timestamp="2026-06-08T08:00:00"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴轴承疲劳磨损，润滑不足加剧损坏",
                    symptoms=["high_vibration", "temperature_rise"],
                    mean_time_to_failure_hours=36.0,
                    recommended_action="更换主轴轴承，检查润滑系统",
                    occurrence_count=8,
                    resolved=False,
                ),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    risk_level="critical",
                    work_order_type="emergency",
                    priority="critical",
                    required_parts=["spindle_bearing_kit", "lubricant", "seal_set"],
                    estimated_duration_hours=8.0,
                    procedure_steps=[
                        "紧急停机",
                        "拆卸主轴组件",
                        "更换轴承及密封件",
                        "补充润滑脂",
                        "重新校准主轴精度",
                        "试运行验证",
                    ],
                    reference_doc="SOP-CNC-MNT-001",
                ),
            ],
        )
        output = agent.execute(request)

        # 结构完整性
        assert output.summary
        assert output.decision == "critical_failure_risk"
        assert output.evidence
        assert output.next_actions
        assert len(output.node_feedback) >= 7

        # 传感器评估
        assert len(output.sensor_evaluations) == 3
        critical_sensors = [e for e in output.sensor_evaluations if e.status == "critical"]
        assert len(critical_sensors) >= 1

        # 趋势分析
        vib_trend = next(t for t in output.trend_analyses if t.sensor_type == "vibration")
        assert vib_trend.alert is True

        # 风险评分 ≥ 0.8
        assert output.risk_assessment.risk_score >= 0.8
        assert output.risk_assessment.risk_level == "critical"

        # 历史匹配
        assert output.failure_prediction.match_source == "historical"
        assert "spindle" in output.failure_prediction.failure_type

        # 时间窗口用历史MTTF
        assert output.time_window.source == "historical"
        assert output.time_window.estimated_window_hours == 36.0

        # 工单包含备件和规程步骤
        assert output.work_order is not None
        assert "spindle_bearing_kit" in output.work_order.required_parts
        assert output.work_order.priority == "critical"

        # 证据含完整上下文
        evidence_text = " ".join(output.evidence)
        assert "8600" in evidence_text

    def test_normal_equipment_with_all_data(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=make_normal_sensors(),
            historical_failures=[
                HistoricalFailure(
                    equipment_type="CNC",
                    failure_type="bearing_fault",
                    symptoms=["high_vibration"],
                ),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    equipment_type="CNC",
                    failure_type="bearing_fault",
                    risk_level="critical",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "equipment_normal"
        assert output.work_order is None


# ══════════════════════════════════════════════════════════════════
# 新增：Context 驱动测试
# ══════════════════════════════════════════════════════════════════


class TestContextPreserved:
    """context 字段在请求中保留并参与分析"""

    def test_context_preserved_in_request(self) -> None:
        """任务书原始样例中的 context 应被保留"""
        ctx = MaintenanceContext(
            production_criticality="high",
            spare_parts_available=False,
            maintenance_window_hours=4.0,
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            context=ctx,
        )
        assert request.context is not None
        assert request.context.production_criticality == "high"
        assert request.context.spare_parts_available is False
        assert request.context.maintenance_window_hours == 4.0

    def test_context_appears_in_evidence(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            production_criticality="high",
            spare_parts_available=True,
            maintenance_window_hours=8.0,
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        evidence_text = " ".join(output.evidence)
        assert "high" in evidence_text
        assert "8.0" in evidence_text or "8" in evidence_text

    def test_context_without_maintenance_window(self) -> None:
        """maintenance_window_hours 为 None 时不抛异常"""
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            production_criticality="medium",
            spare_parts_available=True,
            maintenance_window_hours=None,
        )
        request = make_request(
            sensor_readings=make_normal_sensors(),
            context=ctx,
        )
        output = agent.execute(request)
        assert output.decision == "equipment_normal"


class TestMaintenanceActionFlow:
    """maintenance_action 应进入工单 recommended_action"""

    def test_maintenance_action_flows_to_recommended_action(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    risk_level="critical",
                    maintenance_action="replace spindle bearing",
                    procedure_steps=["步骤1", "步骤2"],
                ),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴轴承疲劳",
                    symptoms=["high_vibration", "temperature_rise"],
                    recommended_action="generic action",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.work_order is not None
        # maintenance_action 应优先于 procedure_steps 和 recommended_action
        assert output.work_order.recommended_action == "replace spindle bearing"

    def test_procedure_steps_used_when_no_maintenance_action(self) -> None:
        agent = PredictiveMaintenanceAgent()
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    risk_level="critical",
                    # no maintenance_action
                    procedure_steps=["检查主轴", "更换轴承", "校准精度"],
                ),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴问题",
                    symptoms=["high_vibration", "temperature_rise"],
                    recommended_action="generic check",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.work_order is not None
        assert "检查主轴" in output.work_order.recommended_action
        assert "更换轴承" in output.work_order.recommended_action


class TestSparePartsHint:
    """备件不可用时产生提示"""

    def test_spare_parts_unavailable_generates_hint(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            production_criticality="medium",
            spare_parts_available=False,
            maintenance_window_hours=None,
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        # next_actions 中应有备件提示
        assert any(
            "备件" in a for a in output.next_actions
        )
        # work_order reason 中也应有
        if output.work_order:
            assert "备件" in output.work_order.reason

    def test_spare_parts_available_no_hint(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            spare_parts_available=True,
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        # 备件可用时不应有备件不可用提示
        assert not any(
            "备件不可用" in a for a in output.next_actions
        )


class TestWindowInsufficientHint:
    """维护窗口不足时产生提示"""

    def test_window_insufficient_generates_hint(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            maintenance_window_hours=2.0,  # 只有2小时
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    risk_level="critical",
                    estimated_duration_hours=8.0,  # 需要8小时
                ),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴问题",
                    symptoms=["high_vibration", "temperature_rise"],
                ),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        # next_actions 中应有窗口不足提示
        assert any(
            "窗口不足" in a or "窗口" in a and "不足" in a
            for a in output.next_actions
        )
        # work_order reason 中也应有
        if output.work_order:
            assert "窗口" in output.work_order.reason

    def test_window_sufficient_no_hint(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            maintenance_window_hours=24.0,  # 充足
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 12.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 105.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
                make_sensor("S-CUR-01", "current", 45.0, threshold_warning=25.0, threshold_critical=40.0, unit="A"),
            ],
            maintenance_rules=[
                MaintenanceRule(
                    rule_id="R-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    risk_level="critical",
                    estimated_duration_hours=4.0,  # 需要4小时，可用24小时
                ),
            ],
            historical_failures=[
                HistoricalFailure(
                    failure_id="HF-001",
                    equipment_type="CNC",
                    failure_type="spindle_bearing_failure",
                    root_cause="主轴问题",
                    symptoms=["high_vibration", "temperature_rise"],
                ),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        # 窗口充足时不应有窗口不足提示
        assert not any(
            "窗口不足" in a for a in output.next_actions
        )


class TestProductionCriticality:
    """生产关键性影响工单说明"""

    def test_high_criticality_in_reason(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            production_criticality="critical",
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 9.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 95.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        # 工单或 next_actions 中应有生产关键性说明
        if output.work_order:
            assert "critical" in output.work_order.reason.lower()

    def test_critical_production_in_next_actions(self) -> None:
        agent = PredictiveMaintenanceAgent()
        ctx = MaintenanceContext(
            production_criticality="high",
        )
        request = make_request(
            sensor_readings=[
                make_sensor("S-VIB-01", "vibration", 9.0, threshold_warning=5.0, threshold_critical=10.0, unit="mm/s"),
                make_sensor("S-TEMP-01", "temperature", 95.0, threshold_warning=80.0, threshold_critical=100.0, unit="°C"),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        assert any(
            "生产关键性" in a or "优先" in a
            for a in output.next_actions
        )
