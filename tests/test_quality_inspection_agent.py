from __future__ import annotations

import pytest

from app.agents.quality_inspection_agent import QualityInspectionAgent, REQUIRED_NODES
from app.schemas.quality_inspection import (
    DefectRecord,
    HistoricalDefect,
    InspectionBatch,
    InspectionContext,
    InspectionItem,
    QualityInspectionRequest,
    QualityStandard,
)


# ══════════════════════════════════════════════════════════════════
# 测试辅助工厂函数
# ══════════════════════════════════════════════════════════════════


def make_batch(**overrides) -> InspectionBatch:
    kwargs = {
        "batch_id": "BATCH-001",
        "product_id": "P-1001",
        "process_step": "CNC machining",
        "inspection_time": "2026-06-08T10:00:00",
        "inspector_id": "INS-001",
    }
    kwargs.update(overrides)
    return InspectionBatch(**kwargs)


def make_standard_items() -> list[InspectionItem]:
    return [
        InspectionItem(
            item_id="ITEM-001",
            metric_name="outer_diameter",
            measured_value=50.02,
            standard_min=49.95,
            standard_max=50.05,
            unit="mm",
            sample_no="S-001",
        ),
        InspectionItem(
            item_id="ITEM-002",
            metric_name="inner_diameter",
            measured_value=30.01,
            standard_min=29.98,
            standard_max=30.02,
            unit="mm",
            sample_no="S-002",
        ),
        InspectionItem(
            item_id="ITEM-003",
            metric_name="surface_roughness",
            measured_value=0.8,
            standard_min=None,
            standard_max=1.6,
            unit="μm",
            sample_no="S-003",
        ),
    ]


def make_request(**overrides) -> QualityInspectionRequest:
    kwargs = {
        "inspection_batch": make_batch(),
        "inspection_items": make_standard_items(),
        "defect_records": [],
        "quality_standards": [],
        "historical_defects": [],
        "context": None,
        "pattern_threshold": 10,
        "environment_data": {},
    }
    kwargs.update(overrides)
    return QualityInspectionRequest(**kwargs)


def make_defect(defect_id: str, defect_type: str, severity="minor", count=1, **kwargs) -> DefectRecord:
    d = {
        "defect_id": defect_id,
        "defect_type": defect_type,
        "severity": severity,
        "count": count,
    }
    d.update(kwargs)
    return DefectRecord(**d)


# ══════════════════════════════════════════════════════════════════
# 新增：任务书原始样例解析
# ══════════════════════════════════════════════════════════════════


class TestTaskSpecSampleParsing:
    """任务书原始输入样例必须可以直接构造 QualityInspectionRequest"""

    def test_task_spec_sample_parses(self) -> None:
        """任务书给出的 JSON 样例应无 ValidationError"""
        sample = {
            "inspection_batch": {
                "batch_id": "BATCH-001",
                "product_id": "P-1001",
                "process_step": "CNC machining",
                "inspection_time": "2026-06-08T10:00:00",
                "inspector_id": "INS-001",
            },
            "inspection_items": [
                {
                    "item_id": "ITEM-001",
                    "metric_name": "outer_diameter",
                    "measured_value": 50.08,
                    "standard_min": 49.95,
                    "standard_max": 50.05,
                    "unit": "mm",
                    "sample_no": "S-001",
                }
            ],
        }
        request = QualityInspectionRequest(**sample)
        assert request.inspection_batch.batch_id == "BATCH-001"
        assert request.inspection_batch.product_id == "P-1001"
        assert request.inspection_batch.process_step == "CNC machining"
        assert len(request.inspection_items) == 1
        assert request.inspection_items[0].metric_name == "outer_diameter"

    def test_task_spec_sample_with_defect_records(self) -> None:
        """扩充：含缺陷记录和质量标准/历史记录，且无 id 字段"""
        sample = {
            "inspection_batch": {
                "batch_id": "BATCH-001",
                "product_id": "P-1001",
                "process_step": "CNC machining",
                "inspection_time": "2026-06-08T10:00:00",
                "inspector_id": "INS-001",
            },
            "inspection_items": [
                {
                    "item_id": "ITEM-001",
                    "metric_name": "outer_diameter",
                    "measured_value": 50.08,
                    "standard_min": 49.95,
                    "standard_max": 50.05,
                    "unit": "mm",
                    "sample_no": "S-001",
                }
            ],
            "defect_records": [
                {
                    "defect_id": "DEF-001",
                    "defect_type": "scratch",
                    "severity": "major",
                    "count": 12,
                }
            ],
            "quality_standards": [
                {
                    "product_id": "P-1001",
                    "metric_name": "outer_diameter",
                    "standard_min": 49.98,
                    "standard_max": 50.02,
                }
            ],
            "historical_defects": [
                {
                    "product_id": "P-1001",
                    "process_step": "CNC machining",
                    "defect_type": "scratch",
                    "root_cause_category": "machine",
                    "root_cause": "刀具磨损",
                }
            ],
        }
        request = QualityInspectionRequest(**sample)
        assert request.defect_records[0].count == 12
        assert request.quality_standards[0].standard_id == ""
        assert request.historical_defects[0].record_id == ""

    def test_count_alias_quantity(self) -> None:
        """count 字段同时兼容 quantity 别名输入"""
        # 用 quantity 输入
        rec = DefectRecord(
            defect_id="DEF-001",
            defect_type="scratch",
            severity="minor",
            quantity=5,  # type: ignore
        )
        assert rec.count == 5

        # 用 count 输入
        rec2 = DefectRecord(
            defect_id="DEF-002",
            defect_type="crack",
            severity="major",
            count=8,
        )
        assert rec2.count == 8

    def test_context_structure(self) -> None:
        """InspectionContext 完整构造"""
        ctx = InspectionContext(
            operator_id="OP-001",
            machine_id="MC-CNC-01",
            material_batch_id="MAT-BATCH-2026-05",
            environment={"temperature": 35.0, "humidity": 62.0},
            process_params={"cutting_speed": 1500.0, "feed_rate": 0.15},
        )
        request = make_request(context=ctx)
        assert request.context.operator_id == "OP-001"
        assert request.context.machine_id == "MC-CNC-01"
        assert request.context.material_batch_id == "MAT-BATCH-2026-05"
        assert request.context.environment["temperature"] == 35.0
        assert request.context.process_params["cutting_speed"] == 1500.0


# ══════════════════════════════════════════════════════════════════
# 新增：count 聚合验证
# ══════════════════════════════════════════════════════════════════


class TestCountAggregation:
    """验证 count 字段被正确聚合（使用 quantity 别名时也一样）"""

    def test_single_record_count_aggregation(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[],
            defect_records=[
                make_defect("DEF-001", "scratch", count=7),
            ],
        )
        output = agent.execute(request)
        assert output.classification is not None
        assert output.classification.by_type["scratch"] == 7

    def test_count_summed_across_records(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[],
            defect_records=[
                make_defect("DEF-001", "scratch", count=4),
                make_defect("DEF-002", "scratch", count=6),
            ],
            pattern_threshold=10,
        )
        output = agent.execute(request)
        # 4 + 6 = 10 >= threshold
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected is True
        assert "scratch" in output.pattern_info.high_frequency_types

    def test_quantity_alias_aggregates_correctly(self) -> None:
        """用 quantity 别名输入，聚合结果应与 count 一致"""
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[],
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="scratch", severity="minor", quantity=3),
                DefectRecord(defect_id="DEF-002", defect_type="scratch", severity="minor", quantity=5),
                DefectRecord(defect_id="DEF-003", defect_type="crack", severity="major", count=2),
            ],
        )
        output = agent.execute(request)
        assert output.classification is not None
        # scratch: 3 + 5 = 8, crack: 2
        assert output.classification.by_type["scratch"] == 8
        assert output.classification.by_type["crack"] == 2

    def test_count_used_in_pattern_detection(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[],
            defect_records=[
                make_defect(f"DEF-{i}", "scratch", count=1)
                for i in range(12)
            ],
            pattern_threshold=10,
        )
        output = agent.execute(request)
        assert output.classification is not None
        assert output.classification.by_type["scratch"] == 12
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected is True


# ══════════════════════════════════════════════════════════════════
# 新增：critical + standard_missing 冲突场景
# ══════════════════════════════════════════════════════════════════


class TestDecisionPriority:
    """critical_quality_issue 必须高于 standard_missing"""

    def test_critical_wins_over_standard_missing(self) -> None:
        """同时存在 critical 缺陷和缺失标准 → critical 必须胜出"""
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            defect_records=[
                DefectRecord(
                    defect_id="DEF-CRIT-001",
                    defect_type="crack",
                    severity="critical",
                    count=1,
                ),
            ],
            quality_standards=[],
        )
        output = agent.execute(request)

        # 必须判定为 critical_quality_issue，不是 standard_missing
        assert output.decision == "critical_quality_issue"

    def test_critical_wins_over_standard_missing_with_context(self) -> None:
        """含完整 context 时 critical 依然优先"""
        agent = QualityInspectionAgent()
        ctx = InspectionContext(
            operator_id="OP-001",
            machine_id="MC-01",
            material_batch_id="MAT-001",
        )
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            defect_records=[
                DefectRecord(
                    defect_id="DEF-CRIT-001",
                    defect_type="crack",
                    severity="critical",
                    count=1,
                ),
            ],
            quality_standards=[],
            context=ctx,
        )
        output = agent.execute(request)
        assert output.decision == "critical_quality_issue"

    def test_standard_missing_without_critical(self) -> None:
        """无 critical 缺陷时 standard_missing 正常判定"""
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            quality_standards=[],
        )
        output = agent.execute(request)
        assert output.decision == "standard_missing"

    def test_critical_overrides_pattern(self) -> None:
        """critical + pattern + standard_missing → critical 胜出"""
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            defect_records=[
                DefectRecord(
                    defect_id="DEF-CRIT-001",
                    defect_type="crack",
                    severity="critical",
                    count=1,
                ),
            ]
            + [
                DefectRecord(
                    defect_id=f"DEF-{i}",
                    defect_type="scratch",
                    severity="minor",
                    count=1,
                )
                for i in range(20)
            ],
            quality_standards=[],
            pattern_threshold=10,
        )
        output = agent.execute(request)
        assert output.decision == "critical_quality_issue"

    def test_pattern_wins_over_root_cause(self) -> None:
        """pattern > historical root_cause"""
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id=f"DEF-{i}",
                    defect_type="scratch",
                    severity="minor",
                    count=1,
                )
                for i in range(15)
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001",
                    product_id="P-1001",
                    process_step="CNC machining",
                    defect_type="scratch",
                    root_cause_category="machine",
                    root_cause="刀具磨损",
                    corrective_action="换刀",
                    occurrence_count=5,
                ),
            ],
            pattern_threshold=10,
        )
        output = agent.execute(request)
        assert output.decision == "defect_pattern_detected"


# ══════════════════════════════════════════════════════════════════
# 新增：标准节点完整性
# ══════════════════════════════════════════════════════════════════


class TestStandardNodes:
    """任务书强制节点必须全部出现"""

    def test_all_required_nodes_present(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                make_defect("DEF-001", "scratch", count=5),
            ],
        )
        output = agent.execute(request)

        node_names = {n.node for n in output.node_feedback}
        for required in REQUIRED_NODES:
            assert required in node_names, f"缺少强制节点: {required}"

    def test_node_count_is_seven(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        # 至少 7 个节点
        node_names = {n.node for n in output.node_feedback}
        assert len(node_names) >= 7

    def test_each_node_has_status_and_message(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        for node in output.node_feedback:
            assert node.node, f"node 标识缺失"
            assert node.status in ("success", "warning", "failed"), (
                f"节点 {node.node} 的 status 不合法: {node.status}"
            )
            assert node.message, f"节点 {node.node} 的 message 为空"

    def test_standard_matching_node_content(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            quality_standards=[
                QualityStandard(
                    product_id="P-1001",
                    metric_name="outer_diameter",
                    standard_min=49.98,
                    standard_max=50.02,
                ),
            ],
        )
        output = agent.execute(request)

        sm_node = next(n for n in output.node_feedback if n.node == "standard_matching")
        assert sm_node.status in ("success", "warning")
        assert "质量标准" in sm_node.message or "匹配" in sm_node.message or "标准" in sm_node.message

    def test_metric_evaluation_node_content(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        me_node = next(n for n in output.node_feedback if n.node == "metric_evaluation")
        assert "合格" in me_node.message or "不合格" in me_node.message or "已评价" in me_node.message

    def test_pattern_detection_node_content(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                make_defect(f"DEF-{i}", "scratch", count=1)
                for i in range(15)
            ],
            pattern_threshold=10,
        )
        output = agent.execute(request)

        pd_node = next(n for n in output.node_feedback if n.node == "pattern_detection")
        assert "检测到缺陷模式" in pd_node.message or "模式" in pd_node.message


# ══════════════════════════════════════════════════════════════════
# 场景 1：无缺陷且指标合格 → quality_passed
# ══════════════════════════════════════════════════════════════════


class TestQualityPassed:
    """全部指标合格，无缺陷记录 → quality_passed"""

    def test_all_indicators_pass_no_defects(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.decision == "quality_passed"
        assert "合格" in output.summary
        assert any("合格" in r.note for r in output.indicator_results)

    def test_output_contains_standard_fields(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert isinstance(output.evidence, list)
        assert isinstance(output.next_actions, list)
        assert isinstance(output.node_feedback, list)

    def test_passed_batch_has_next_actions(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        assert len(output.next_actions) >= 1
        assert any("监控" in a or "质检" in a for a in output.next_actions)

    def test_no_false_evidence(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        assert not any("不合格" in e for e in output.evidence)


# ══════════════════════════════════════════════════════════════════
# 场景 2：指标超出标准 → quality_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestQualityRiskDetected:
    """指标不合格但未形成模式 → quality_risk_detected"""

    def test_out_of_spec_indicator_detected(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="outer_diameter",
                    measured_value=50.08,
                    standard_min=49.95,
                    standard_max=50.05,
                    unit="mm",
                    sample_no="S-001",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "quality_risk_detected"
        assert any(not r.passed for r in output.indicator_results)

    def test_below_min_indicator_detected(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="outer_diameter",
                    measured_value=49.90,
                    standard_min=49.95,
                    standard_max=50.05,
                    unit="mm",
                    sample_no="S-001",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "quality_risk_detected"
        failed = [r for r in output.indicator_results if not r.passed]
        assert len(failed) == 1
        assert failed[0].deviation < 0

    def test_mixed_pass_fail_indicators(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="outer_diameter",
                    measured_value=50.02,
                    standard_min=49.95,
                    standard_max=50.05,
                    unit="mm",
                ),
                InspectionItem(
                    item_id="ITEM-002",
                    metric_name="inner_diameter",
                    measured_value=35.00,
                    standard_min=29.98,
                    standard_max=30.02,
                    unit="mm",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "quality_risk_detected"
        passed = [r for r in output.indicator_results if r.passed]
        failed = [r for r in output.indicator_results if not r.passed]
        assert len(passed) == 1
        assert len(failed) == 1

    def test_single_defect_no_pattern(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001",
                    defect_type="scratch",
                    severity="minor",
                    location="surface",
                    count=3,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "quality_risk_detected"
        assert output.classification is not None
        assert output.classification.total_defects == 3


# ══════════════════════════════════════════════════════════════════
# 场景 3：高频缺陷模式 → defect_pattern_detected
# ══════════════════════════════════════════════════════════════════


class TestDefectPatternDetected:
    """同一缺陷类型 count >= 阈值 → defect_pattern_detected"""

    def test_high_frequency_single_type(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            pattern_threshold=10,
            defect_records=[
                DefectRecord(
                    defect_id=f"DEF-{i}",
                    defect_type="scratch",
                    severity="minor",
                    location="surface",
                    count=1,
                )
                for i in range(12)
            ],
        )
        output = agent.execute(request)

        assert output.decision == "defect_pattern_detected"
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected is True
        assert "scratch" in output.pattern_info.high_frequency_types

    def test_multiple_high_frequency_types(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            pattern_threshold=5,
            defect_records=[
                DefectRecord(defect_id=f"SCR-{i}", defect_type="scratch", severity="minor", count=1)
                for i in range(8)
            ]
            + [
                DefectRecord(defect_id=f"CRK-{i}", defect_type="crack", severity="major", count=1)
                for i in range(6)
            ],
        )
        output = agent.execute(request)

        assert output.decision == "defect_pattern_detected"
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected is True
        assert len(output.pattern_info.high_frequency_types) >= 2

    def test_below_threshold_no_pattern(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            pattern_threshold=10,
            defect_records=[
                DefectRecord(defect_id=f"DEF-{i}", defect_type="scratch", severity="minor", count=1)
                for i in range(5)
            ],
        )
        output = agent.execute(request)

        assert output.decision != "defect_pattern_detected"
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected is False

    def test_custom_threshold(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            pattern_threshold=3,
            defect_records=[
                DefectRecord(defect_id=f"DEF-{i}", defect_type="scratch", severity="minor", count=1)
                for i in range(4)
            ],
        )
        output = agent.execute(request)

        assert output.decision == "defect_pattern_detected"

    def test_location_clustering(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            pattern_threshold=5,
            defect_records=[
                DefectRecord(defect_id=f"DEF-{i}", defect_type="scratch", severity="minor",
                             location="surface", count=1)
                for i in range(10)
            ],
        )
        output = agent.execute(request)

        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected


# ══════════════════════════════════════════════════════════════════
# 场景 4：Critical 缺陷 → critical_quality_issue
# ══════════════════════════════════════════════════════════════════


class TestCriticalQualityIssue:
    """任一 critical 缺陷 → critical_quality_issue"""

    def test_single_critical_defect(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-CRIT-001",
                    defect_type="crack",
                    severity="critical",
                    location="edge",
                    count=1,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "critical_quality_issue"
        assert output.classification is not None
        assert len(output.classification.critical_items) >= 1

    def test_multiple_critical_defects(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id=f"DEF-CRIT-{i}", defect_type="size_deviation",
                             severity="critical", count=1)
                for i in range(3)
            ],
        )
        output = agent.execute(request)

        assert output.decision == "critical_quality_issue"
        assert len(output.classification.critical_items) == 3

    def test_critical_triggers_immediate_action(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-CRIT-001",
                    defect_type="crack",
                    severity="critical",
                    location="load_bearing",
                    count=1,
                ),
            ],
        )
        output = agent.execute(request)

        assert any(
            "立即" in a or "紧急" in a or "隔离" in a or "异常处理" in a
            for a in output.next_actions
        )


# ══════════════════════════════════════════════════════════════════
# 场景 5：历史缺陷匹配根因 → root_cause_identified
# ══════════════════════════════════════════════════════════════════


class TestRootCauseIdentified:
    """历史记录匹配到明确根因 → root_cause_identified"""

    def test_historical_match_returns_root_cause(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001",
                    defect_type="size_deviation",
                    severity="major",
                    location="outer_diameter",
                    count=3,  # below threshold
                    product_id="P-1001",
                    process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001",
                    product_id="P-1001",
                    process_step="CNC machining",
                    defect_type="size_deviation",
                    root_cause_category="machine",
                    root_cause="CNC 主轴跳动超差 0.02mm，导致外径尺寸不稳定",
                    corrective_action="校准 CNC 主轴，每班首件检验增加外径测量频次",
                    occurrence_count=8,
                    resolved=True,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "root_cause_identified"
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "machine"
        assert output.root_cause_result.match_source == "historical"
        assert output.root_cause_result.confidence >= 0.8

    def test_historical_match_evidence_included(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001",
                    defect_type="size_deviation",
                    severity="major",
                    count=3,
                    product_id="P-1001",
                    process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001",
                    product_id="P-1001",
                    process_step="CNC machining",
                    defect_type="size_deviation",
                    root_cause_category="machine",
                    root_cause="主轴跳动",
                    corrective_action="校准主轴",
                    occurrence_count=5,
                    resolved=False,
                ),
            ],
        )
        output = agent.execute(request)

        assert len(output.root_cause_result.matched_evidence) >= 1
        assert "HIST-001" in output.root_cause_result.matched_evidence[0]

    def test_no_historical_match_falls_back_to_rules(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001",
                    defect_type="scratch",
                    severity="major",
                    count=3,
                    product_id="P-1001",
                    process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001",
                    product_id="P-9999",
                    process_step="other",
                    defect_type="other",
                    root_cause_category="machine",
                    root_cause="不相关",
                    corrective_action="不相关",
                    occurrence_count=1,
                    resolved=True,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.match_source in ("rule_based", "none")

    def test_historical_match_with_unknown_category(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001",
                    defect_type="scratch",
                    severity="major",
                    count=5,
                    product_id="P-1001",
                    process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001",
                    product_id="P-1001",
                    process_step="CNC machining",
                    defect_type="scratch",
                    root_cause_category="unknown",
                    root_cause="",
                    corrective_action="",
                    occurrence_count=2,
                    resolved=False,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category != "unknown"


# ══════════════════════════════════════════════════════════════════
# 场景 6：缺少质量标准 → standard_missing
# ══════════════════════════════════════════════════════════════════


class TestStandardMissing:
    """缺少质量标准且无法使用自带上下限 → standard_missing"""

    def test_no_standard_source_and_no_builtin_limits(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                    sample_no="S-001",
                ),
            ],
            quality_standards=[],
        )
        output = agent.execute(request)

        assert output.decision == "standard_missing"
        assert any(
            r.standard_source == "none" for r in output.indicator_results
        )

    def test_quality_standards_provide_limits(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=62.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            quality_standards=[
                QualityStandard(
                    standard_id="QS-001",
                    product_id="P-1001",
                    metric_name="hardness",
                    standard_min=55.0,
                    standard_max=65.0,
                    unit="HRC",
                    source="GB/T 230.1-2018",
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "quality_passed"
        assert all(r.passed for r in output.indicator_results)

    def test_quality_standards_overrides_inspection_item_limits(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="outer_diameter",
                    measured_value=50.02,
                    standard_min=49.90,
                    standard_max=50.10,
                    unit="mm",
                ),
            ],
            quality_standards=[
                QualityStandard(
                    standard_id="QS-001",
                    product_id="P-1001",
                    metric_name="outer_diameter",
                    standard_min=49.98,
                    standard_max=50.02,
                    unit="mm",
                    source="GB/T 1184-1996",
                ),
            ],
        )
        output = agent.execute(request)

        assert all(r.standard_source == "quality_standards" for r in output.indicator_results)
        assert output.decision == "quality_passed"

    def test_standard_missing_next_actions(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001",
                    metric_name="hardness",
                    measured_value=58.0,
                    standard_min=None,
                    standard_max=None,
                    unit="HRC",
                ),
            ],
            quality_standards=[],
        )
        output = agent.execute(request)

        assert any("标准" in a for a in output.next_actions)


# ══════════════════════════════════════════════════════════════════
# 场景 7：环境异常推断为 environment
# ══════════════════════════════════════════════════════════════════


class TestEnvironmentRootCause:
    """环境温度/湿度异常 → environment 根因"""

    def test_high_temperature_infers_environment(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="size_deviation",
                             severity="major", count=5),
            ],
            environment_data={"temperature": 42.0, "humidity": 55.0},
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "environment"
        assert "42" in output.root_cause_result.root_cause

    def test_low_temperature_infers_environment(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="crack",
                             severity="major", count=3, process_step="welding"),
            ],
            environment_data={"temperature": -5.0, "humidity": 40.0},
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "environment"

    def test_high_humidity_infers_environment(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="corrosion",
                             severity="major", count=3),
            ],
            environment_data={"temperature": 25.0, "humidity": 90.0},
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "environment"

    def test_chinese_env_keys(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="size_deviation",
                             severity="major", count=5),
            ],
            environment_data={"温度": 45.0, "湿度": 60.0},
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "environment"

    def test_context_environment_takes_priority(self) -> None:
        """context.environment 应优先于 environment_data"""
        agent = QualityInspectionAgent()
        ctx = InspectionContext(
            environment={"temperature": 42.0},
        )
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="size_deviation",
                             severity="major", count=5),
            ],
            environment_data={"temperature": 25.0},  # 正常但会被 context 覆盖
            context=ctx,
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "environment"

    def test_normal_environment_no_env_inference(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="size_deviation",
                             severity="major", count=5),
            ],
            environment_data={"temperature": 25.0, "humidity": 55.0},
        )
        output = agent.execute(request)

        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "machine"


# ══════════════════════════════════════════════════════════════════
# 场景 8：设备/材料/方法/人员根因推断
# ══════════════════════════════════════════════════════════════════


class TestMachineRootCause:
    """设备相关缺陷 → machine"""

    def test_size_deviation_infers_machine(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="尺寸超差",
                             severity="major", count=5),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "machine"

    def test_surface_roughness_infers_machine(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="表面粗糙",
                             severity="major", count=5, process_step="grinding"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "machine"

    def test_outer_diameter_infers_machine(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="外径",
                             severity="major", count=5),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "machine"

    def test_scratch_defect_infers_machine(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="scratch",
                             severity="minor", count=5, process_step="assembly"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "machine"

    def test_material_crack_infers_material(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="裂纹",
                             severity="critical", count=1, process_step="forging"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "material"

    def test_hardness_infers_material(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="硬度异常",
                             severity="major", count=5, process_step="heat_treatment"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "material"

    def test_inclusion_infers_material(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="inclusion",
                             severity="major", count=3, process_step="casting"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "material"

    def test_method_keyword_infers_method(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="process_parameter",
                             severity="major", count=5, process_step="heat_treatment"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "method"

    def test_man_keyword_infers_man(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="operator_error",
                             severity="major", count=3, process_step="assembly"),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result.root_cause_category == "man"

    def test_process_step_based_inference_fallback(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="unknown_defect_xyz",
                             severity="minor", count=2),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "machine"

    def test_unknown_defect_with_unknown_process(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_batch=make_batch(process_step="unknown_process"),
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="xyz_unknown",
                             severity="minor", count=2),
            ],
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "unknown"


# ══════════════════════════════════════════════════════════════════
# Context 驱动的根因推断
# ══════════════════════════════════════════════════════════════════


class TestContextDrivenRootCause:
    """InspectionContext 驱动更精确的根因推断"""

    def test_context_machine_id_drives_machine(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(machine_id="MC-CNC-01")
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="dimension_error",
                             severity="major", count=3),
            ],
            context=ctx,
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "machine"
        assert "MC-CNC-01" in " ".join(output.root_cause_result.matched_evidence)

    def test_context_material_batch_drives_material(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(material_batch_id="MAT-B2026")
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="crack",
                             severity="major", count=3),
            ],
            context=ctx,
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "material"
        assert "MAT-B2026" in " ".join(output.root_cause_result.matched_evidence)

    def test_context_operator_drives_man(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(operator_id="OP-005")
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="operator_error",
                             severity="major", count=3),
            ],
            context=ctx,
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "man"

    def test_context_process_params_drives_method(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(process_params={"cutting_speed": 2000.0})
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="generic_defect",
                             severity="minor", count=3),
            ],
            context=ctx,
        )
        output = agent.execute(request)
        assert output.root_cause_result is not None
        assert output.root_cause_result.root_cause_category == "method"

    def test_context_evidence_in_output(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(
            operator_id="OP-001",
            machine_id="MC-01",
            material_batch_id="MAT-001",
        )
        request = make_request(
            defect_records=[
                DefectRecord(defect_id="DEF-001", defect_type="scratch",
                             severity="major", count=5),
            ],
            context=ctx,
        )
        output = agent.execute(request)

        evidence_text = " ".join(output.evidence)
        assert "OP-001" in evidence_text
        assert "MC-01" in evidence_text
        assert "MAT-001" in evidence_text


# ══════════════════════════════════════════════════════════════════
# 输入校验边界测试
# ══════════════════════════════════════════════════════════════════


class TestInputValidation:
    """输入校验边界测试"""

    def test_empty_items_and_defects(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(inspection_items=[], defect_records=[])
        output = agent.execute(request)

        validation_node = next(n for n in output.node_feedback if n.node == "input_validation")
        assert validation_node.status == "failed"

    def test_invalid_batch_detected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QualityInspectionRequest(
                inspection_batch=None,  # type: ignore
                inspection_items=make_standard_items(),
            )

    def test_valid_input_passes(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        validation_node = next(n for n in output.node_feedback if n.node == "input_validation")
        assert validation_node.status == "success"

    def test_only_defects_no_items(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            inspection_items=[],
            defect_records=[DefectRecord(defect_id="DEF-001", defect_type="scratch", count=2)],
        )
        output = agent.execute(request)

        validation_node = next(n for n in output.node_feedback if n.node == "input_validation")
        assert validation_node.status == "success"

    def test_only_items_no_defects(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(inspection_items=make_standard_items(), defect_records=[])
        output = agent.execute(request)

        validation_node = next(n for n in output.node_feedback if n.node == "input_validation")
        assert validation_node.status == "success"


# ══════════════════════════════════════════════════════════════════
# 输出结构完整性测试
# ══════════════════════════════════════════════════════════════════


class TestOutputStructure:
    """验证输出结构完整性与字段一致性"""

    def test_summary_mentions_batch_id(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)
        assert "BATCH-001" in output.summary

    def test_decision_is_valid_enum(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request()
        output = agent.execute(request)

        valid_decisions = {
            "quality_passed",
            "quality_risk_detected",
            "defect_pattern_detected",
            "critical_quality_issue",
            "root_cause_identified",
            "standard_missing",
        }
        assert output.decision in valid_decisions

    def test_next_actions_are_non_empty_for_risks(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[DefectRecord(defect_id="DEF-001", defect_type="crack",
                                          severity="critical", count=1)],
        )
        output = agent.execute(request)
        assert len(output.next_actions) >= 1

    def test_recommendations_generated_for_defects(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[DefectRecord(defect_id="DEF-001", defect_type="size_deviation",
                                          severity="major", count=15)],
        )
        output = agent.execute(request)
        assert len(output.recommendations) >= 1
        for rec in output.recommendations:
            assert rec.priority in ("critical", "major", "minor")
            assert rec.action

    def test_plan_returns_valid_result(self) -> None:
        agent = QualityInspectionAgent()
        result = agent.plan("需要质量分析", {})
        assert result.summary
        assert result.decision
        assert len(result.next_actions) >= 2

    def test_build_node_feedback_returns_generic_nodes(self) -> None:
        agent = QualityInspectionAgent()
        result = agent.plan("质量分析", {})
        nodes = agent.build_node_feedback("质量分析", result)
        assert len(nodes) == 3
        assert all(n.status == "completed" for n in nodes)
        node_names = {n.node_name for n in nodes}
        assert "意图识别" in node_names
        assert "决策输出" in node_names


# ══════════════════════════════════════════════════════════════════
# RAG 预留接口测试
# ══════════════════════════════════════════════════════════════════


class TestRAGInterfaces:
    """验证 RAG 预留接口功能正确性"""

    def test_match_quality_standard_exact(self) -> None:
        from app.services.quality_inspection_service import QualityInspectionService

        service = QualityInspectionService()
        standards = [
            QualityStandard(
                standard_id="QS-001", product_id="P-1001",
                metric_name="outer_diameter", standard_min=49.95, standard_max=50.05, unit="mm",
            ),
            QualityStandard(
                standard_id="QS-002", product_id="P-1002",
                metric_name="hardness", standard_min=55.0, standard_max=65.0, unit="HRC",
            ),
        ]

        result = service.match_quality_standard("P-1001", "outer_diameter", standards)
        assert result is not None
        assert result.standard_id == "QS-001"

        result_none = service.match_quality_standard("P-9999", "outer_diameter", standards)
        assert result_none is None

    def test_match_historical_defect_exact(self) -> None:
        from app.services.quality_inspection_service import QualityInspectionService

        service = QualityInspectionService()
        history = [
            HistoricalDefect(
                record_id="HIST-001", product_id="P-1001",
                process_step="CNC machining", defect_type="size_deviation",
                root_cause_category="machine", root_cause="主轴跳动",
                corrective_action="校准主轴",
            ),
        ]

        result = service.match_historical_defect(
            "P-1001", "CNC machining", "size_deviation", history
        )
        assert result is not None
        assert result.record_id == "HIST-001"

        result_none = service.match_historical_defect(
            "P-9999", "CNC machining", "size_deviation", history
        )
        assert result_none is None


# ══════════════════════════════════════════════════════════════════
# 综合场景测试
# ══════════════════════════════════════════════════════════════════


class TestComprehensiveScenarios:
    """端到端综合场景"""

    def test_full_pipeline_with_all_data(self) -> None:
        agent = QualityInspectionAgent()
        ctx = InspectionContext(
            operator_id="INS-001",
            machine_id="MC-CNC-01",
            material_batch_id="MAT-B2026-001",
            environment={"temperature": 28.0, "humidity": 60.0},
        )
        request = make_request(
            inspection_items=[
                InspectionItem(
                    item_id="ITEM-001", metric_name="outer_diameter",
                    measured_value=50.08, standard_min=49.95, standard_max=50.05, unit="mm",
                ),
                InspectionItem(
                    item_id="ITEM-002", metric_name="hardness",
                    measured_value=58.0, standard_min=None, standard_max=None, unit="HRC",
                ),
            ],
            quality_standards=[
                QualityStandard(
                    standard_id="QS-001", product_id="P-1001",
                    metric_name="hardness", standard_min=55.0, standard_max=65.0, unit="HRC",
                ),
            ],
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001", defect_type="scratch", severity="major",
                    location="surface", count=12,
                    product_id="P-1001", process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001", product_id="P-1001",
                    process_step="CNC machining", defect_type="scratch",
                    root_cause_category="machine",
                    root_cause="CNC 刀具磨损导致表面划伤",
                    corrective_action="更换刀具并增加检查频次",
                    occurrence_count=5, resolved=True,
                ),
            ],
            pattern_threshold=10,
            environment_data={"temperature": 28.0, "humidity": 60.0},
            context=ctx,
        )
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert output.evidence
        assert output.next_actions
        assert len(output.node_feedback) >= 7

        # ITEM-001 不合格
        item1 = next(r for r in output.indicator_results if r.item_id == "ITEM-001")
        assert item1.passed is False

        # ITEM-002 使用 quality_standards
        item2 = next(r for r in output.indicator_results if r.item_id == "ITEM-002")
        assert item2.passed is True
        assert item2.standard_source == "quality_standards"

        # 缺陷模式检测
        assert output.pattern_info is not None
        assert output.pattern_info.pattern_detected

        # 根因匹配历史
        assert output.root_cause_result is not None
        assert output.root_cause_result.match_source == "historical"

        # context evidence
        evidence_text = " ".join(output.evidence)
        assert "MC-CNC-01" in evidence_text
        assert "INS-001" in evidence_text
        assert "MAT-B2026-001" in evidence_text

    def test_single_defect_root_cause_identified(self) -> None:
        agent = QualityInspectionAgent()
        request = make_request(
            defect_records=[
                DefectRecord(
                    defect_id="DEF-001", defect_type="scratch",
                    severity="minor", count=3,
                    product_id="P-1001", process_step="CNC machining",
                ),
            ],
            historical_defects=[
                HistoricalDefect(
                    record_id="HIST-001", product_id="P-1001",
                    process_step="CNC machining", defect_type="scratch",
                    root_cause_category="machine",
                    root_cause="刀具磨损导致划伤",
                    corrective_action="定期更换刀具",
                    occurrence_count=3,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "root_cause_identified"
        assert output.root_cause_result.match_source == "historical"
