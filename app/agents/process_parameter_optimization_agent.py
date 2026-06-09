from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentResult, BaseAgent
from app.schemas.agent import NodeFeedback
from app.schemas.process_parameter_optimization import (
    AgentDecision,
    ProcessNodeFeedback,
    ProcessParameterOptimizationOutput,
    ProcessParameterOptimizationRequest,
)
from app.services.process_parameter_optimization_service import (
    ProcessParameterOptimizationService,
)

REQUIRED_NODES = [
    "input_validation",
    "historical_data_analysis",
    "parameter_constraint_check",
    "quality_correlation_analysis",
    "best_batch_selection",
    "parameter_recommendation",
    "risk_assessment",
    "optimization_summary_generation",
]


class ProcessParameterOptimizationAgent(BaseAgent):
    """工艺参数优化智能体。

    8 节点流程：
    input_validation → historical_data_analysis → parameter_constraint_check
    → quality_correlation_analysis → best_batch_selection
    → parameter_recommendation → risk_assessment → optimization_summary_generation
    """

    name = "process_parameter_optimization"
    display_name = "工艺参数优化"
    scenario_hint = "工艺参数、质量优化、良品率、缺陷率、节拍、参数推荐"

    def __init__(self) -> None:
        self.service = ProcessParameterOptimizationService()

    def execute(
        self, request: ProcessParameterOptimizationRequest
    ) -> ProcessParameterOptimizationOutput:
        nodes: list[ProcessNodeFeedback] = []
        svc = self.service

        # ── 0. 输入校验 ───────────────────────────────────
        batches = svc.match_process_history(
            request.process.process_id,
            request.process.product_id,
            request.historical_batches,
        )
        constraints = svc.match_parameter_constraints(
            request.process.process_id, request.parameter_constraints
        )

        node_ok, issues = svc.validate_batch_count(batches)
        if not node_ok:
            nodes.append(
                ProcessNodeFeedback(
                    node="input_validation", status="warning",
                    message=f"输入校验：{issues}",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="input_validation", status="success",
                    message=f"输入校验通过：{issues}，约束 {len(constraints)} 条",
                )
            )

        # ── 1. 历史数据分析 ───────────────────────────────
        if len(batches) >= 3:
            nodes.append(
                ProcessNodeFeedback(
                    node="historical_data_analysis", status="success",
                    message=f"历史数据分析完成：{len(batches)} 个批次，"
                            f"平均良品率 {sum(b.yield_rate for b in batches)/len(batches):.2%}",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="historical_data_analysis", status="warning",
                    message=f"历史数据不足（{len(batches)} 条），分析结果仅供参考",
                )
            )

        # ── 2. 参数约束检查 ───────────────────────────────
        violations = svc.check_parameter_constraints(
            request.current_parameters, constraints
        )
        has_safety = svc.has_safety_critical_violation(violations)

        if has_safety:
            nodes.append(
                ProcessNodeFeedback(
                    node="parameter_constraint_check", status="failed",
                    message=f"安全关键参数越界：{len([v for v in violations if v.safety_critical])} 个",
                )
            )
        elif violations:
            nodes.append(
                ProcessNodeFeedback(
                    node="parameter_constraint_check", status="warning",
                    message=f"参数越界：{len(violations)} 个",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="parameter_constraint_check", status="success",
                    message="所有参数在约束范围内",
                )
            )

        # ── 3. 质量相关性分析 ─────────────────────────────
        correlations = svc.correlate_parameters_with_quality(batches)
        non_neutral = [c for c in correlations if c.trend != "neutral"]
        if non_neutral:
            nodes.append(
                ProcessNodeFeedback(
                    node="quality_correlation_analysis", status="success",
                    message=f"参数-质量相关性分析完成：{len(correlations)} 个参数，"
                            f"{len(non_neutral)} 个非中性趋势",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="quality_correlation_analysis", status="warning",
                    message=f"参数-质量相关性分析完成：{len(correlations)} 个参数，均无明显趋势",
                )
            )

        # ── 4. 最佳批次选择 ───────────────────────────────
        config = request.optimization_config
        best_batch, best_score = svc.select_best_batch(batches, config.optimize_for)

        # 目标冲突检测
        conflicting = svc.check_conflicting_targets(
            batches, config.min_yield_rate, config.max_defect_rate,
            config.target_cycle_time_minutes,
        )

        if best_batch:
            nodes.append(
                ProcessNodeFeedback(
                    node="best_batch_selection", status="success",
                    message=f"最佳批次：{best_batch.batch_id}，评分 {best_score}，"
                            f"优化目标：{config.optimize_for}",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="best_batch_selection", status="warning",
                    message="无法选出最佳批次（无历史数据）",
                )
            )

        # ── 5. 推荐参数生成 ───────────────────────────────
        recommendations = svc.generate_recommendations(
            request.current_parameters, best_batch, constraints
        )
        clamped = [r for r in recommendations if r.clamped]
        if recommendations:
            msg = f"已生成 {len(recommendations)} 条推荐参数"
            if clamped:
                msg += f"（{len(clamped)} 条被约束 clamp）"
            nodes.append(
                ProcessNodeFeedback(
                    node="parameter_recommendation", status="success", message=msg,
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="parameter_recommendation", status="warning",
                    message="无推荐参数（缺少最佳批次数据）",
                )
            )

        # ── 6. 风险评估 ───────────────────────────────────
        quality_at_risk, avg_yield, avg_defect = svc.assess_quality_risk(
            batches, config.min_yield_rate, config.max_defect_rate
        )

        risk_msgs: list[str] = []
        if has_safety:
            risk_msgs.append("安全关键参数越界")
        if violations:
            risk_msgs.append(f"{len(violations)} 个参数越界")
        if conflicting:
            risk_msgs.append("质量与效率目标冲突")
        if quality_at_risk:
            risk_msgs.append(f"历史质量低于目标（良品率 {avg_yield:.2%}，缺陷率 {avg_defect:.2%})")
        if len(batches) < 3:
            risk_msgs.append("历史数据不足")

        if risk_msgs:
            nodes.append(
                ProcessNodeFeedback(
                    node="risk_assessment",
                    status="failed" if has_safety else "warning",
                    message="风险评估：" + "；".join(risk_msgs),
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="risk_assessment", status="success",
                    message="未检测到明显风险",
                )
            )

        # ── 7. 改进建议 ───────────────────────────────────
        improvement = svc.compute_expected_improvements(best_batch, batches)
        near_optimal = svc.is_current_near_optimal(
            request.current_parameters, best_batch
        )
        if near_optimal:
            nodes.append(
                ProcessNodeFeedback(
                    node="optimization_summary_generation", status="success",
                    message="当前参数已接近最优，无需大幅调整",
                )
            )
        elif best_batch:
            nodes.append(
                ProcessNodeFeedback(
                    node="optimization_summary_generation", status="success",
                    message=f"改进建议已生成：{improvement.description}",
                )
            )
        else:
            nodes.append(
                ProcessNodeFeedback(
                    node="optimization_summary_generation", status="warning",
                    message="数据不足，无法生成改进建议",
                )
            )

        # ── 8. 决策 ───────────────────────────────────────
        decision = self._derive_decision(
            has_safety, violations, batches, conflicting,
            quality_at_risk, near_optimal, recommendations,
        )

        return self._build_output(
            request, batches, correlations, violations, recommendations,
            best_batch, best_score, conflicting, improvement,
            near_optimal, decision, nodes,
        )

    # ── 决策 ─────────────────────────────────────────────────

    @staticmethod
    def _derive_decision(
        has_safety: bool,
        violations: list,
        batches: list,
        conflicting: bool,
        quality_at_risk: bool,
        near_optimal: bool,
        recommendations: list,
    ) -> AgentDecision:
        """按任务书优先级推导决策。"""
        if has_safety:
            return "safety_risk_detected"
        if violations:
            return "parameter_out_of_range"
        if len(batches) < 3:
            return "insufficient_history_data"
        if conflicting:
            return "conflicting_targets"
        if quality_at_risk:
            return "quality_risk_detected"
        if not near_optimal and recommendations:
            return "optimization_recommended"
        return "parameters_optimal"

    # ── 输出组装 ─────────────────────────────────────────────

    @staticmethod
    def _build_output(
        request, batches, correlations, violations, recommendations,
        best_batch, best_score, conflicting, improvement,
        near_optimal, decision, nodes,
    ) -> ProcessParameterOptimizationOutput:
        return ProcessParameterOptimizationOutput(
            summary=ProcessParameterOptimizationAgent._make_summary(
                request, batches, violations, best_batch, decision,
            ),
            decision=decision,
            evidence=ProcessParameterOptimizationAgent._make_evidence(
                batches, violations, correlations, best_batch, recommendations,
            ),
            next_actions=ProcessParameterOptimizationAgent._make_next_actions(
                decision, violations, recommendations, best_batch,
            ),
            node_feedback=nodes,
            parameter_correlations=correlations,
            constraint_violations=violations,
            recommended_parameters=recommendations,
            improvement_estimate=improvement,
            best_batch_id=best_batch.batch_id if best_batch else "",
            best_batch_score=best_score,
            conflicting_targets_detected=conflicting,
        )

    @staticmethod
    def _make_summary(request, batches, violations, best_batch, decision) -> str:
        dc: dict[str, str] = {
            "safety_risk_detected": "安全关键参数越界，需立即处理。",
            "parameter_out_of_range": "当前参数超出约束范围。",
            "insufficient_history_data": "历史数据不足，分析结果仅供参考。",
            "conflicting_targets": "质量目标与效率目标存在冲突。",
            "quality_risk_detected": "历史质量低于目标值。",
            "optimization_recommended": "已生成优化参数推荐。",
            "parameters_optimal": "当前参数已接近最优。",
        }
        proc = request.process
        base = (
            f"工艺 {proc.process_id}（{proc.process_name}/{proc.process_step}），"
            f"历史批次 {len(batches)} 条"
        )
        parts = [base, dc.get(decision, "")]
        if violations:
            parts.append(f"参数越界 {len(violations)} 个")
        if best_batch:
            parts.append(f"推荐参考批次 {best_batch.batch_id}")
        return "。".join(p for p in parts if p) + "。"

    @staticmethod
    def _make_evidence(batches, violations, correlations, best_batch, recommendations):
        ev: list[str] = []
        ev.append(f"历史批次 {len(batches)} 条")
        for v in violations:
            ev.append(
                f"[constraint_violation] {v.parameter_name}: "
                f"当前 {v.current_value}，范围 [{v.min_value}, {v.max_value}]"
                + (" (安全关键)" if v.safety_critical else "")
            )
        for c in correlations:
            if c.trend != "neutral":
                ev.append(f"[correlation] {c.parameter_name}: {c.trend} — {c.description}")
        if best_batch:
            ev.append(
                f"[best_batch] {best_batch.batch_id}: "
                f"良品率 {best_batch.yield_rate:.2%}，缺陷率 {best_batch.defect_rate:.2%}"
            )
        for r in recommendations[:8]:
            ev.append(
                f"[recommendation] {r.parameter_name}: "
                f"{r.current_value} → {r.recommended_value}"
                + (" (clamped)" if r.clamped else "")
            )
        return ev

    @staticmethod
    def _make_next_actions(decision, violations, recommendations, best_batch):
        actions: list[str] = []
        if decision == "safety_risk_detected":
            actions.append("立即暂停涉及安全关键参数的工艺操作。")
            for v in violations:
                if v.safety_critical:
                    actions.append(
                        f"调整 {v.parameter_name} 至 [{v.min_value}, {v.max_value}] 范围内。"
                    )
        if decision == "parameter_out_of_range":
            for v in violations[:5]:
                actions.append(
                    f"调整 {v.parameter_name}: {v.current_value} → "
                    f"[{v.min_value}, {v.max_value}]"
                )
        if decision == "insufficient_history_data":
            actions.append("积累更多历史批次数据（建议至少 3 条）后重新分析。")
        if decision == "conflicting_targets":
            actions.append("重新评估质量与效率目标的可行性。")
            actions.append("考虑放宽节拍目标或接受当前良品率水平。")
        if decision in ("optimization_recommended", "quality_risk_detected"):
            if best_batch:
                actions.append(f"参考批次 {best_batch.batch_id} 的参数组合进行工艺验证。")
            for r in recommendations[:5]:
                actions.append(
                    f"调整 {r.parameter_name}: {r.current_value} → {r.recommended_value}"
                )
        if decision == "parameters_optimal":
            actions.append("保持当前参数继续生产。")
            actions.append("定期监控良品率和缺陷率趋势。")
        return actions

    # ── BaseAgent 接口 ──────────────────────────────────────

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        return AgentResult(
            summary=f"工艺参数优化智能体已接收请求：{request_text[:80]}",
            decision="optimization_recommended",
            evidence=["建议通过结构化接口 execute() 传入工艺数据。"],
            next_actions=["提供工艺信息、历史批次、参数约束数据。"],
        )

    def build_node_feedback(
        self, request_text: str, result: AgentResult
    ) -> list[NodeFeedback]:
        now = datetime.now(tz=timezone.utc)
        return [
            NodeFeedback(
                node_id=f"{self.name}-intent",
                node_name="意图识别",
                status="completed",
                detail=f"已识别为{self.display_name}场景",
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-analysis",
                node_name="规则分析",
                status="completed",
                detail=result.summary,
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-decision",
                node_name="决策输出",
                status="completed",
                detail=result.decision,
                started_at=now,
                completed_at=now,
            ),
        ]
