from __future__ import annotations

import pytest

from app.agents.process_parameter_optimization_agent import (
    REQUIRED_NODES,
    ProcessParameterOptimizationAgent,
)
from app.schemas.process_parameter_optimization import (
    CurrentParameter,
    HistoricalBatch,
    OptimizationConfig,
    ParameterConstraint,
    ProcessInfo,
    ProcessParameterOptimizationRequest,
)
from app.services.process_parameter_optimization_service import (
    ProcessParameterOptimizationService,
)


# ══════════════════════════════════════════════════════════════════
# 工厂函数
# ══════════════════════════════════════════════════════════════════


def make_process(process_id="PROC-001", name="heat treatment", product_id="P-1001",
                 step="quenching") -> ProcessInfo:
    return ProcessInfo(
        process_id=process_id, process_name=name,
        product_id=product_id, process_step=step,
    )


def make_constraint(param="temperature", min_v=800.0, max_v=900.0,
                    safety=False, unit="°C") -> ParameterConstraint:
    return ParameterConstraint(
        parameter_name=param, min_value=min_v, max_value=max_v,
        safety_critical=safety, unit=unit,
    )


def make_batch(batch_id="BATCH-001", params=None, yield_rate=0.95, defect_rate=0.03,
               cycle_time=5.0, throughput=12.0, deviation=0.01,
               quality_score=0.9, quality_passed=True) -> HistoricalBatch:
    return HistoricalBatch(
        batch_id=batch_id,
        parameters=params or {"temperature": 860, "pressure": 10.0, "speed": 120.0},
        yield_rate=yield_rate, defect_rate=defect_rate,
        cycle_time_minutes=cycle_time, throughput_per_hour=throughput,
        dimension_deviation=deviation, quality_score=quality_score,
        quality_passed=quality_passed,
    )


def make_current_param(name="temperature", value=860.0) -> CurrentParameter:
    return CurrentParameter(parameter_name=name, value=value)


def make_config(optimize_for="balanced", min_yield=0.9, max_defect=0.05,
                target_cycle=0.0) -> OptimizationConfig:
    return OptimizationConfig(
        optimize_for=optimize_for, min_yield_rate=min_yield,
        max_defect_rate=max_defect, target_cycle_time_minutes=target_cycle,
    )


def make_request(**overrides) -> ProcessParameterOptimizationRequest:
    kwargs = {
        "process": make_process(),
        "historical_batches": [
            make_batch("B001", {"temperature": 850, "pressure": 10, "speed": 100},
                       yield_rate=0.92, defect_rate=0.04, cycle_time=6.0, throughput=10.0),
            make_batch("B002", {"temperature": 860, "pressure": 12, "speed": 120},
                       yield_rate=0.95, defect_rate=0.03, cycle_time=5.0, throughput=12.0),
            make_batch("B003", {"temperature": 870, "pressure": 11, "speed": 110},
                       yield_rate=0.94, defect_rate=0.035, cycle_time=5.5, throughput=11.0),
        ],
        "parameter_constraints": [
            make_constraint("temperature", 800, 900, safety=True),
            make_constraint("pressure", 5, 20),
            make_constraint("speed", 80, 150),
        ],
        "current_parameters": [
            make_current_param("temperature", 860),
            make_current_param("pressure", 12),
            make_current_param("speed", 120),
        ],
        "quality_feedback": [],
        "optimization_config": make_config(),
    }
    kwargs.update(overrides)
    return ProcessParameterOptimizationRequest(**kwargs)


# ══════════════════════════════════════════════════════════════════
# 场景 1：当前参数接近最佳 → parameters_optimal
# ══════════════════════════════════════════════════════════════════


class TestParametersOptimal:
    def test_current_near_best_returns_optimal(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.decision == "parameters_optimal"
        assert "接近最优" in output.summary or "最优" in output.summary

    def test_all_nodes_present(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request()
        output = agent.execute(request)

        node_names = {n.node for n in output.node_feedback}
        for rn in REQUIRED_NODES:
            assert rn in node_names, f"Missing node: {rn}"

    def test_output_structure_complete(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert isinstance(output.evidence, list)
        assert isinstance(output.next_actions, list)
        assert len(output.node_feedback) >= 8
        assert len(output.recommended_parameters) >= 1


# ══════════════════════════════════════════════════════════════════
# 场景 2：推荐优化参数 → optimization_recommended
# ══════════════════════════════════════════════════════════════════


class TestOptimizationRecommended:
    def test_different_params_triggers_recommendation(self) -> None:
        """当前参数与最佳批次差异大 → optimization_recommended。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            current_parameters=[
                make_current_param("temperature", 820),  # 远离最优 860
                make_current_param("pressure", 8),
                make_current_param("speed", 90),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "optimization_recommended"
        assert len(output.recommended_parameters) >= 1
        # 推荐参数应明显不同
        temp_rec = next(r for r in output.recommended_parameters if r.parameter_name == "temperature")
        assert temp_rec.recommended_value != 820

    def test_poor_yield_triggers_optimization(self) -> None:
        """历史批次良品率差异大，推荐优化。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B001", {"temperature": 830}, yield_rate=0.85, defect_rate=0.08, cycle_time=6.0, throughput=10.0),
                make_batch("B002", {"temperature": 860}, yield_rate=0.96, defect_rate=0.02, cycle_time=5.0, throughput=12.0),
                make_batch("B003", {"temperature": 850}, yield_rate=0.88, defect_rate=0.06, cycle_time=5.5, throughput=11.0),
            ],
            current_parameters=[make_current_param("temperature", 830)],
        )
        output = agent.execute(request)

        # 当前参数接近低良品率批次 → 需要优化
        assert output.decision in ("optimization_recommended", "quality_risk_detected")


# ══════════════════════════════════════════════════════════════════
# 场景 3：参数超出普通约束 → parameter_out_of_range
# ══════════════════════════════════════════════════════════════════


class TestParameterOutOfRange:
    def test_below_min_triggers_out_of_range(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            parameter_constraints=[
                make_constraint("temperature", 800, 900, safety=False),
                make_constraint("pressure", 5, 20),
                make_constraint("speed", 80, 150),
            ],
            current_parameters=[
                make_current_param("temperature", 750),  # below min 800
                make_current_param("pressure", 12),
                make_current_param("speed", 120),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "parameter_out_of_range"
        assert len(output.constraint_violations) >= 1
        assert output.constraint_violations[0].parameter_name == "temperature"
        assert output.constraint_violations[0].violation_type == "below_min"

    def test_above_max_triggers_out_of_range(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            parameter_constraints=[
                make_constraint("temperature", 800, 900, safety=False),
            ],
            current_parameters=[make_current_param("temperature", 950)],
        )
        output = agent.execute(request)

        assert output.decision == "parameter_out_of_range"
        assert output.constraint_violations[0].violation_type == "above_max"


# ══════════════════════════════════════════════════════════════════
# 场景 4：安全关键参数越界 → safety_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestSafetyRiskDetected:
    def test_safety_critical_violation_triggers_safety_risk(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            current_parameters=[make_current_param("temperature", 950)],  # above max, safety_critical
        )
        output = agent.execute(request)

        assert output.decision == "safety_risk_detected"
        assert any("安全" in a for a in output.next_actions)

    def test_safety_risk_next_actions_specific(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            current_parameters=[make_current_param("temperature", 750)],
        )
        output = agent.execute(request)

        # temperature is safety_critical → safety_risk_detected
        assert output.decision == "safety_risk_detected"
        # next_actions should mention the specific parameter
        assert any("temperature" in a for a in output.next_actions)


# ══════════════════════════════════════════════════════════════════
# 场景 5：历史数据不足 → insufficient_history_data
# ══════════════════════════════════════════════════════════════════


class TestInsufficientHistoryData:
    def test_fewer_than_3_batches_triggers_insufficient(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B001", {"temperature": 850}),
                make_batch("B002", {"temperature": 860}),
            ],
            current_parameters=[make_current_param("temperature", 860)],
        )
        output = agent.execute(request)

        assert output.decision == "insufficient_history_data"

    def test_insufficient_but_still_outputs_analysis(self) -> None:
        """数据不足时仍应输出基础分析。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[make_batch("B001", {"temperature": 850})],
            current_parameters=[make_current_param("temperature", 860)],
        )
        output = agent.execute(request)

        assert output.decision == "insufficient_history_data"
        # 仍应有基本输出
        assert output.summary
        assert len(output.node_feedback) >= 1


# ══════════════════════════════════════════════════════════════════
# 场景 6：质量与效率目标冲突 → conflicting_targets
# ══════════════════════════════════════════════════════════════════


class TestConflictingTargets:
    def test_quality_efficiency_conflict(self) -> None:
        """高质量批次不满足节拍，高效率批次不满足质量 → 冲突。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                # 高质量但慢
                make_batch("B-HQ", {"temp": 840}, yield_rate=0.96, defect_rate=0.02, cycle_time=10.0, throughput=6.0),
                # 高效率但质量差
                make_batch("B-HE", {"temp": 880}, yield_rate=0.85, defect_rate=0.08, cycle_time=3.0, throughput=20.0),
                # 另一个
                make_batch("B-MID", {"temp": 860}, yield_rate=0.90, defect_rate=0.05, cycle_time=6.0, throughput=10.0),
            ],
            optimization_config=make_config(
                min_yield=0.9, max_defect=0.05, target_cycle=4.0,  # 严格节拍目标
            ),
        )
        output = agent.execute(request)

        assert output.decision == "conflicting_targets"
        assert output.conflicting_targets_detected

    def test_no_conflict_when_joint_batch_exists(self) -> None:
        """存在同时满足质量和效率的批次 → 不冲突。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B-OK", {"temp": 860}, yield_rate=0.95, defect_rate=0.03, cycle_time=5.0, throughput=12.0),
                make_batch("B-OK2", {"temp": 850}, yield_rate=0.93, defect_rate=0.04, cycle_time=5.5, throughput=11.0),
                make_batch("B-OK3", {"temp": 870}, yield_rate=0.94, defect_rate=0.035, cycle_time=5.0, throughput=12.0),
            ],
            optimization_config=make_config(
                min_yield=0.9, max_defect=0.05, target_cycle=6.0,
            ),
        )
        output = agent.execute(request)

        assert not output.conflicting_targets_detected
        assert output.decision != "conflicting_targets"


# ══════════════════════════════════════════════════════════════════
# 场景 7：质量低于目标 → quality_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestQualityRiskDetected:
    def test_low_average_quality_triggers_risk(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B001", {"temp": 830}, yield_rate=0.82, defect_rate=0.09, cycle_time=6.0, throughput=10.0),
                make_batch("B002", {"temp": 840}, yield_rate=0.85, defect_rate=0.07, cycle_time=5.5, throughput=11.0),
                make_batch("B003", {"temp": 850}, yield_rate=0.86, defect_rate=0.08, cycle_time=5.0, throughput=12.0),
            ],
            optimization_config=make_config(min_yield=0.9, max_defect=0.05),
            current_parameters=[make_current_param("temperature", 845)],
        )
        output = agent.execute(request)

        # avg_yield ~0.84 < 0.9 min_yield → quality_risk_detected
        assert output.decision == "quality_risk_detected"


# ══════════════════════════════════════════════════════════════════
# 场景 8：quality_first → 选高良品率低缺陷批次
# ══════════════════════════════════════════════════════════════════


class TestQualityFirstSelection:
    def test_quality_first_selects_best_quality(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B-LOW", {"temp": 830}, yield_rate=0.85, defect_rate=0.07, cycle_time=4.0, throughput=15.0),
                make_batch("B-HIGH", {"temp": 860}, yield_rate=0.98, defect_rate=0.01, cycle_time=6.0, throughput=10.0),
                make_batch("B-MID", {"temp": 840}, yield_rate=0.90, defect_rate=0.04, cycle_time=5.0, throughput=12.0),
            ],
            optimization_config=make_config(optimize_for="quality_first"),
        )
        output = agent.execute(request)

        # quality_first → 应选 B-HIGH（最高良品率 0.98，最低缺陷率 0.01）
        assert output.best_batch_id == "B-HIGH"

    def test_quality_first_ignores_cycle_time(self) -> None:
        """quality_first 不应被节拍影响选择。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B-SLOW", {"temp": 860}, yield_rate=0.97, defect_rate=0.02, cycle_time=15.0, throughput=4.0),
                make_batch("B-FAST", {"temp": 850}, yield_rate=0.92, defect_rate=0.04, cycle_time=3.0, throughput=20.0),
                make_batch("B-MID", {"temp": 855}, yield_rate=0.94, defect_rate=0.03, cycle_time=8.0, throughput=7.5),
            ],
            optimization_config=make_config(optimize_for="quality_first"),
        )
        output = agent.execute(request)

        # 即使 B-SLOW 很慢，quality_first 仍选它（最高质量）
        assert output.best_batch_id == "B-SLOW"


# ══════════════════════════════════════════════════════════════════
# 场景 9：balanced → 综合选择质量和效率
# ══════════════════════════════════════════════════════════════════


class TestBalancedSelection:
    def test_balanced_selects_joint_quality_efficiency(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B-Q", {"temp": 860}, yield_rate=0.97, defect_rate=0.02, cycle_time=10.0, throughput=6.0),
                make_batch("B-E", {"temp": 830}, yield_rate=0.75, defect_rate=0.15, cycle_time=3.0, throughput=20.0),
                make_batch("B-BAL", {"temp": 850}, yield_rate=0.96, defect_rate=0.02, cycle_time=5.0, throughput=16.0),
            ],
            optimization_config=make_config(optimize_for="balanced"),
        )
        output = agent.execute(request)

        # balanced 应选 B-BAL（质量和效率都较好）
        assert output.best_batch_id == "B-BAL"


# ══════════════════════════════════════════════════════════════════
# 场景 10：推荐参数被约束 clamp
# ══════════════════════════════════════════════════════════════════


class TestConstraintClamping:
    def test_recommendation_clamped_to_constraints(self) -> None:
        """最佳批次参数超出约束时，推荐参数被 clamp。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                make_batch("B001", {"temperature": 950, "pressure": 25}, yield_rate=0.99, defect_rate=0.005, cycle_time=4.0, throughput=15.0),
                make_batch("B002", {"temperature": 860, "pressure": 12}, yield_rate=0.91, defect_rate=0.04, cycle_time=6.0, throughput=9.0),
                make_batch("B003", {"temperature": 870, "pressure": 11}, yield_rate=0.92, defect_rate=0.04, cycle_time=5.5, throughput=10.0),
            ],
            # constraint: temp 800-900, pressure 5-20
            parameter_constraints=[
                make_constraint("temperature", 800, 900),
                make_constraint("pressure", 5, 20),
            ],
            current_parameters=[
                make_current_param("temperature", 860),
                make_current_param("pressure", 12),
            ],
        )
        output = agent.execute(request)

        temp_rec = next(r for r in output.recommended_parameters if r.parameter_name == "temperature")
        pressure_rec = next(r for r in output.recommended_parameters if r.parameter_name == "pressure")

        # 最佳批次 temp=950 > max 900 → clamped to 900
        assert temp_rec.recommended_value == 900.0
        assert temp_rec.clamped is True
        # 最佳批次 pressure=25 > max 20 → clamped to 20
        assert pressure_rec.recommended_value == 20.0
        assert pressure_rec.clamped is True


# ══════════════════════════════════════════════════════════════════
# 场景 11：相关性分析 → 非 neutral 趋势
# ══════════════════════════════════════════════════════════════════


class TestParameterCorrelation:
    def test_correlation_produces_non_neutral_trend(self) -> None:
        """有明显质量差异的参数应产生非 neutral 趋势。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                # 低温 → 低良品率
                make_batch("B1", {"temp": 810}, yield_rate=0.80, defect_rate=0.08, cycle_time=5.0, throughput=12.0),
                make_batch("B2", {"temp": 820}, yield_rate=0.82, defect_rate=0.07, cycle_time=5.0, throughput=12.0),
                # 高温 → 高良品率
                make_batch("B3", {"temp": 870}, yield_rate=0.94, defect_rate=0.03, cycle_time=5.0, throughput=12.0),
                make_batch("B4", {"temp": 880}, yield_rate=0.96, defect_rate=0.02, cycle_time=5.0, throughput=12.0),
            ],
            parameter_constraints=[make_constraint("temp", 800, 900)],
            current_parameters=[make_current_param("temp", 860)],
        )
        output = agent.execute(request)

        correlations = output.parameter_correlations
        assert len(correlations) >= 1
        # 应该有非 neutral 趋势（高温 → 高质量）
        non_neutral = [c for c in correlations if c.trend != "neutral"]
        assert len(non_neutral) >= 1

    def test_efficiency_tradeoff_detected(self) -> None:
        """质量-效率权衡应被检测为 efficiency_tradeoff。"""
        agent = ProcessParameterOptimizationAgent()
        request = make_request(
            historical_batches=[
                # 低速高质量
                make_batch("B1", {"speed": 80}, yield_rate=0.96, defect_rate=0.02, cycle_time=8.0, throughput=7.5),
                make_batch("B2", {"speed": 90}, yield_rate=0.95, defect_rate=0.025, cycle_time=7.0, throughput=8.5),
                # 高速低质量
                make_batch("B3", {"speed": 130}, yield_rate=0.85, defect_rate=0.07, cycle_time=4.0, throughput=15.0),
                make_batch("B4", {"speed": 140}, yield_rate=0.83, defect_rate=0.08, cycle_time=3.5, throughput=17.0),
            ],
            parameter_constraints=[make_constraint("speed", 50, 200)],
            current_parameters=[make_current_param("speed", 120)],
        )
        output = agent.execute(request)

        speed_corr = next((c for c in output.parameter_correlations if c.parameter_name == "speed"), None)
        assert speed_corr is not None
        # 高速：quality worse but faster → efficiency_tradeoff
        assert speed_corr.trend in ("efficiency_tradeoff", "negative_quality_correlation")


# ══════════════════════════════════════════════════════════════════
# 场景 12：服务层单元测试
# ══════════════════════════════════════════════════════════════════


class TestServiceLayer:
    def test_validate_batch_count(self) -> None:
        svc = ProcessParameterOptimizationService()
        ok, msg = svc.validate_batch_count([make_batch("B1")])
        assert not ok
        ok, msg = svc.validate_batch_count([make_batch(f"B{i}") for i in range(3)])
        assert ok

    def test_check_parameter_constraints(self) -> None:
        svc = ProcessParameterOptimizationService()
        violations = svc.check_parameter_constraints(
            [make_current_param("temp", 750)],
            [make_constraint("temp", 800, 900, safety=True)],
        )
        assert len(violations) == 1
        assert violations[0].safety_critical

    def test_select_best_batch_quality_first(self) -> None:
        svc = ProcessParameterOptimizationService()
        batches = [
            make_batch("B1", {"t": 1}, yield_rate=0.85, defect_rate=0.06, cycle_time=5.0, throughput=10.0),
            make_batch("B2", {"t": 2}, yield_rate=0.97, defect_rate=0.02, cycle_time=5.0, throughput=10.0),
        ]
        best, score = svc.select_best_batch(batches, "quality_first")
        assert best is not None
        assert best.batch_id == "B2"

    def test_is_current_near_optimal(self) -> None:
        svc = ProcessParameterOptimizationService()
        best = make_batch("BEST", {"t": 860, "p": 12})
        # close params
        close = [make_current_param("t", 865), make_current_param("p", 11.5)]
        assert svc.is_current_near_optimal(close, best)

        # far params
        far = [make_current_param("t", 800), make_current_param("p", 6)]
        assert not svc.is_current_near_optimal(far, best)

    def test_improvement_estimate(self) -> None:
        svc = ProcessParameterOptimizationService()
        batches = [
            make_batch("B1", yield_rate=0.85, defect_rate=0.06, cycle_time=6.0, throughput=10.0),
            make_batch("B2", yield_rate=0.90, defect_rate=0.04, cycle_time=5.0, throughput=12.0),
            make_batch("B3", yield_rate=0.95, defect_rate=0.02, cycle_time=4.0, throughput=15.0),
        ]
        best, _ = svc.select_best_batch(batches, "quality_first")
        imp = svc.compute_expected_improvements(best, batches)

        assert imp.expected_yield_rate_delta > 0  # best > avg
        assert imp.expected_defect_rate_delta < 0  # best defect < avg defect
        assert imp.description

    def test_conflicting_targets_detection(self) -> None:
        svc = ProcessParameterOptimizationService()
        batches = [
            make_batch("B1", yield_rate=0.95, defect_rate=0.02, cycle_time=10.0, throughput=6.0),
            make_batch("B2", yield_rate=0.85, defect_rate=0.08, cycle_time=3.0, throughput=20.0),
            make_batch("B3", yield_rate=0.90, defect_rate=0.05, cycle_time=6.0, throughput=10.0),
        ]
        # target cycle 4.0 → B1 质量好但太慢，B2 快但质量差 → 冲突
        assert svc.check_conflicting_targets(batches, 0.9, 0.05, 4.0)

        # target cycle 12.0 → B1 满足 → 不冲突
        assert not svc.check_conflicting_targets(batches, 0.9, 0.05, 12.0)


# ══════════════════════════════════════════════════════════════════
# 场景 13：AgentResult 接口
# ══════════════════════════════════════════════════════════════════


class TestAgentResultInterface:
    def test_plan_returns_result(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        result = agent.plan("需要优化热处理工艺参数", {})
        assert result.summary
        assert result.decision

    def test_build_node_feedback(self) -> None:
        agent = ProcessParameterOptimizationAgent()
        result = agent.plan("工艺优化", {})
        nodes = agent.build_node_feedback("工艺优化", result)
        assert len(nodes) == 3
        assert nodes[0].node_name == "意图识别"


# ══════════════════════════════════════════════════════════════════
# RAG 预留接口验证
# ══════════════════════════════════════════════════════════════════


class TestRAGStubs:
    def test_match_process_history(self) -> None:
        svc = ProcessParameterOptimizationService()
        batches = [make_batch("B1"), make_batch("B2")]
        result = svc.match_process_history("PROC-001", "P-1001", batches)
        assert len(result) == 2

    def test_match_parameter_constraints(self) -> None:
        svc = ProcessParameterOptimizationService()
        constraints = [make_constraint("t", 0, 100)]
        result = svc.match_parameter_constraints("PROC-001", constraints)
        assert len(result) == 1

    def test_match_quality_feedback(self) -> None:
        svc = ProcessParameterOptimizationService()
        from app.schemas.process_parameter_optimization import QualityFeedback
        fb = [QualityFeedback(batch_id="B1", feedback_text="test")]
        result = svc.match_quality_feedback("B1", fb)
        assert len(result) == 1
        result_empty = svc.match_quality_feedback("B99", fb)
        assert len(result_empty) == 0


# ══════════════════════════════════════════════════════════════════
# 验收：任务书原始样例解析
# ══════════════════════════════════════════════════════════════════

TASK_BOOK_SAMPLE: dict = {
    "process": {
        "process_id": "PROC-001",
        "process_name": "heat treatment",
        "product_id": "P-1001",
        "process_step": "quenching",
    },
    "historical_batches": [
        {
            "batch_id": "BATCH-001",
            "parameters": {"temperature": 840, "pressure": 10.0, "speed": 100},
            "quality_metrics": {
                "yield_rate": 0.92,
                "defect_rate": 0.04,
                "quality_score": 0.88,
                "quality_passed": True,
            },
            "production_metrics": {
                "cycle_time_minutes": 6.0,
                "throughput_per_hour": 10.0,
            },
        },
        {
            "batch_id": "BATCH-002",
            "parameters": {"temperature": 860, "pressure": 12.0, "speed": 120},
            "quality_metrics": {
                "yield_rate": 0.95,
                "defect_rate": 0.03,
                "quality_score": 0.92,
                "quality_passed": True,
            },
            "production_metrics": {
                "cycle_time_minutes": 5.0,
                "throughput_per_hour": 12.0,
            },
        },
        {
            "batch_id": "BATCH-003",
            "parameters": {"temperature": 870, "pressure": 11.0, "speed": 110},
            "quality_metrics": {
                "yield_rate": 0.94,
                "defect_rate": 0.035,
                "quality_score": 0.90,
                "quality_passed": True,
            },
            "production_metrics": {
                "cycle_time_minutes": 5.5,
                "throughput_per_hour": 11.0,
            },
        },
    ],
    "current_parameters": {
        "temperature": 820,
        "pressure": 1.1,
        "speed": 90,
    },
    "parameter_constraints": [
        {"parameter_name": "temperature", "min_value": 800, "max_value": 900,
         "safety_critical": True, "unit": "°C"},
        {"parameter_name": "pressure", "min_value": 5, "max_value": 20,
         "safety_critical": False, "unit": "bar"},
        {"parameter_name": "speed", "min_value": 80, "max_value": 150,
         "safety_critical": False, "unit": "rpm"},
    ],
    "quality_targets": {
        "optimize_for": "balanced",
        "min_yield_rate": 0.9,
        "max_defect_rate": 0.05,
    },
}


class TestTaskBookSampleParsing:
    """任务书原始样例直接构造请求并执行。"""

    def test_task_book_sample_parses_without_error(self) -> None:
        """ProcessParameterOptimizationRequest(**任务书样例) 不抛 ValidationError。"""
        request = ProcessParameterOptimizationRequest(**TASK_BOOK_SAMPLE)
        assert request.process.process_id == "PROC-001"
        assert len(request.historical_batches) == 3
        # current_parameters 从 dict 转为 list
        assert len(request.current_parameters) == 3
        cp_map = {cp.parameter_name: cp.value for cp in request.current_parameters}
        assert cp_map["temperature"] == 820
        assert cp_map["pressure"] == 1.1
        assert cp_map["speed"] == 90
        # quality_targets → optimization_config
        assert request.optimization_config.optimize_for == "balanced"
        assert request.optimization_config.min_yield_rate == 0.9

    def test_task_book_sample_nested_metrics_expanded(self) -> None:
        """quality_metrics / production_metrics 展开为扁平字段。"""
        request = ProcessParameterOptimizationRequest(**TASK_BOOK_SAMPLE)
        b1 = request.historical_batches[0]
        assert b1.yield_rate == 0.92
        assert b1.defect_rate == 0.04
        assert b1.quality_score == 0.88
        assert b1.cycle_time_minutes == 6.0
        assert b1.throughput_per_hour == 10.0

    def test_task_book_sample_full_pipeline(self) -> None:
        """任务书样例完整执行，断言节点、best batch、推荐参数均有输出。"""
        agent = ProcessParameterOptimizationAgent()
        request = ProcessParameterOptimizationRequest(**TASK_BOOK_SAMPLE)
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        # 最佳批次有值
        assert output.best_batch_id != ""
        assert output.best_batch_score > 0
        # 推荐参数有输出
        assert len(output.recommended_parameters) >= 1
        # 所有标准节点存在（含 historical_data_analysis / optimization_summary_generation）
        node_names = {n.node for n in output.node_feedback}
        for rn in REQUIRED_NODES:
            assert rn in node_names, f"Missing node: {rn}"
        # 节点数 >= 8
        assert len(output.node_feedback) >= 8
