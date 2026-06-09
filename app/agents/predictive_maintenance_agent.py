from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentResult, BaseAgent
from app.schemas.agent import NodeFeedback
from app.schemas.predictive_maintenance import (
    AgentDecision,
    FailurePrediction,
    MaintenanceNodeFeedback,
    PredictiveMaintenanceOutput,
    PredictiveMaintenanceRequest,
    RiskAssessment,
    TimeWindowEstimate,
    TrendAnalysisResult,
    WorkOrderSuggestion,
)
from app.services.predictive_maintenance_service import PredictiveMaintenanceService

REQUIRED_NODES = [
    "input_validation",
    "sensor_evaluation",
    "trend_analysis",
    "failure_prediction",
    "historical_failure_matching",
    "maintenance_rule_matching",
    "work_order_generation",
]


class PredictiveMaintenanceAgent(BaseAgent):
    """设备预测性维护智能体。

    职责：编排预测性维护分析流程，调用 service 完成：
    - 输入校验 (input_validation)
    - 传感器状态评估 (sensor_evaluation)
    - 趋势分析 (trend_analysis)
    - 故障预测 (failure_prediction)
    - 历史故障匹配 (historical_failure_matching)
    - 维护规程匹配 (maintenance_rule_matching)
    - 维护工单生成 (work_order_generation)

    输出标准化 AgentResult 与节点式反馈。
    不直接访问数据库、不直接调用模型客户端。
    """

    name = "predictive_maintenance"
    display_name = "设备预测性维护"
    scenario_hint = "设备、振动、温度、电流、传感器、故障、维护、停机"

    def __init__(self) -> None:
        self.service = PredictiveMaintenanceService()

    # ── 主入口 ────────────────────────────────────────────────

    def execute(
        self, request: PredictiveMaintenanceRequest
    ) -> PredictiveMaintenanceOutput:
        """执行设备预测性维护全流程。"""
        nodes: list[MaintenanceNodeFeedback] = []

        # 1. 输入校验
        if not self._validate_input(request, nodes):
            return self._build_error_output("sensor_data_insufficient", nodes)

        # 2. 传感器评估
        sensor_evals = self._evaluate_sensors(request, nodes)

        # 3. 趋势分析
        trend_results = self._analyze_trends(request, nodes)

        # 4. 风险评估
        risk = self._assess_risk(request, sensor_evals, nodes)

        # 5. 故障预测 + 历史匹配
        failure_pred = self._predict_failure(request, sensor_evals, nodes)

        # 6. 维护规程匹配
        rule_matched = self._match_maintenance_rule(request, failure_pred, risk, nodes)

        # 7. 时间窗口
        time_window = self._estimate_time_window(risk, failure_pred, nodes)

        # 8. 推导决策 + 工单
        decision = self._derive_decision(
            request, sensor_evals, risk, failure_pred, rule_matched
        )
        work_order = self._generate_work_order(
            request, risk, failure_pred, time_window, decision, nodes
        )

        # 9. 汇总输出
        return self._build_output(
            request, sensor_evals, trend_results, risk,
            failure_pred, time_window, work_order, decision, nodes,
        )

    # ── 步骤 1：输入校验 ─────────────────────────────────────

    @staticmethod
    def _validate_input(
        request: PredictiveMaintenanceRequest,
        nodes: list[MaintenanceNodeFeedback],
    ) -> bool:
        issues: list[str] = []

        if not request.equipment:
            issues.append("设备信息缺失")
        if not request.sensor_readings:
            issues.append("传感器读数为空")

        if issues:
            nodes.append(
                MaintenanceNodeFeedback(
                    node="input_validation",
                    status="failed",
                    message="输入校验失败：" + "；".join(issues),
                )
            )
            return False

        eq = request.equipment
        status_note = ""
        if eq.running_status != "running":
            status_note = (
                f"（注意：设备处于 {eq.running_status} 状态，"
                "传感器异常可能是计划停机导致）"
            )

        nodes.append(
            MaintenanceNodeFeedback(
                node="input_validation",
                status="success",
                message=(
                    f"输入校验通过：设备 {eq.equipment_id}（{eq.equipment_name}），"
                    f"类型 {eq.equipment_type}，状态 {eq.running_status}，"
                    f"传感器读数 {len(request.sensor_readings)} 条，"
                    f"历史故障 {len(request.historical_failures)} 条，"
                    f"维护规程 {len(request.maintenance_rules)} 条"
                    + status_note
                ),
            )
        )
        return True

    # ── 步骤 2：传感器评估 ───────────────────────────────────

    @staticmethod
    def _evaluate_sensors(
        request: PredictiveMaintenanceRequest,
        nodes: list[MaintenanceNodeFeedback],
    ) -> list:
        service = PredictiveMaintenanceService()
        evaluations = service.evaluate_all_sensors(request.sensor_readings)

        normal_count = sum(1 for e in evaluations if e.status == "normal")
        warning_count = sum(1 for e in evaluations if e.status == "warning")
        critical_count = sum(1 for e in evaluations if e.status == "critical")

        status: str = "success"
        if critical_count > 0:
            status = "warning"
        if critical_count == len(evaluations) and len(evaluations) > 0:
            status = "failed"

        nodes.append(
            MaintenanceNodeFeedback(
                node="sensor_evaluation",
                status=status,
                message=(
                    f"传感器评估完成：共 {len(evaluations)} 个传感器，"
                    f"normal {normal_count}，warning {warning_count}，"
                    f"critical {critical_count}"
                ),
            )
        )
        return evaluations

    # ── 步骤 3：趋势分析 ─────────────────────────────────────

    @staticmethod
    def _analyze_trends(
        request: PredictiveMaintenanceRequest,
        nodes: list[MaintenanceNodeFeedback],
    ) -> list[TrendAnalysisResult]:
        service = PredictiveMaintenanceService()
        trends = service.analyze_trends(
            request.sensor_readings,
            rise_threshold_pct=request.trend_rise_threshold_pct,
        )

        alert_count = sum(1 for t in trends if t.alert)
        alert_types = [t.sensor_type for t in trends if t.alert]

        status: str = "success"
        detail = (
            f"趋势分析完成：覆盖 {len(trends)} 种传感器类型"
        )
        if alert_count > 0:
            status = "warning"
            detail += f"，{alert_count} 种出现趋势异常：{'、'.join(alert_types)}"
        else:
            detail += "，未检测到趋势异常"

        nodes.append(
            MaintenanceNodeFeedback(
                node="trend_analysis",
                status=status,
                message=detail,
            )
        )
        return trends

    # ── 步骤 4：风险评估 ─────────────────────────────────────

    @staticmethod
    def _assess_risk(
        request: PredictiveMaintenanceRequest,
        sensor_evals: list,
        nodes: list[MaintenanceNodeFeedback],
    ) -> RiskAssessment:
        service = PredictiveMaintenanceService()
        risk = service.assess_risk(sensor_evals, request.equipment)
        # 风险评分作为内部计算步骤，不单独产生节点反馈；
        # 风险信息融入 trend_analysis 和 failure_prediction 节点。
        return risk

    # ── 步骤 5：故障预测 + 历史匹配 ──────────────────────────

    @staticmethod
    def _predict_failure(
        request: PredictiveMaintenanceRequest,
        sensor_evals: list,
        nodes: list[MaintenanceNodeFeedback],
    ) -> FailurePrediction:
        service = PredictiveMaintenanceService()
        failure_pred = service.predict_failure(
            equipment_type=request.equipment.equipment_type,
            evaluations=sensor_evals,
            historical_failures=request.historical_failures,
        )

        # 故障预测节点
        pred_status: str = "success"
        if failure_pred.match_source == "none":
            pred_status = "warning"

        nodes.append(
            MaintenanceNodeFeedback(
                node="failure_prediction",
                status=pred_status,
                message=(
                    f"故障预测：{failure_pred.failure_type}，"
                    f"来源={failure_pred.match_source}，"
                    f"置信度={failure_pred.confidence:.0%}"
                ),
            )
        )

        # 历史故障匹配节点
        hist_status: str = "success"
        hist_msg: str
        if failure_pred.match_source == "historical":
            hist_msg = (
                f"历史故障匹配成功：{failure_pred.failure_type}，"
                f"根因={failure_pred.root_cause[:80]}"
            )
        elif request.historical_failures:
            hist_msg = "未找到匹配的历史故障记录，已使用规则推断。"
            hist_status = "warning"
        else:
            hist_msg = "无历史故障库，已使用规则推断。"
            hist_status = "warning"

        nodes.append(
            MaintenanceNodeFeedback(
                node="historical_failure_matching",
                status=hist_status,
                message=hist_msg,
            )
        )
        return failure_pred

    # ── 步骤 6：维护规程匹配 ─────────────────────────────────

    @staticmethod
    def _match_maintenance_rule(
        request: PredictiveMaintenanceRequest,
        failure_pred: FailurePrediction,
        risk: RiskAssessment,
        nodes: list[MaintenanceNodeFeedback],
    ) -> bool:
        service = PredictiveMaintenanceService()
        rule = service.match_maintenance_rule(
            equipment_type=request.equipment.equipment_type,
            failure_type=failure_pred.failure_type,
            risk_level=risk.risk_level,
            maintenance_rules=request.maintenance_rules,
        )

        if rule is not None:
            nodes.append(
                MaintenanceNodeFeedback(
                    node="maintenance_rule_matching",
                    status="success",
                    message=(
                        f"维护规程匹配成功：{rule.rule_id or '(无编号)'}，"
                        f"工单类型={rule.work_order_type}，"
                        f"预计工时={rule.estimated_duration_hours}h"
                    ),
                )
            )
            return True
        else:
            nodes.append(
                MaintenanceNodeFeedback(
                    node="maintenance_rule_matching",
                    status="warning",
                    message="未匹配到维护规程，将使用默认建议。",
                )
            )
            return False

    # ── 步骤 7：时间窗口 ─────────────────────────────────────

    @staticmethod
    def _estimate_time_window(
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        nodes: list[MaintenanceNodeFeedback],
    ) -> TimeWindowEstimate:
        service = PredictiveMaintenanceService()
        tw = service.estimate_time_window(risk.risk_level, failure_pred)
        # 时间窗口信息已融合进 work_order_generation 节点
        return tw

    # ── 决策推导 ──────────────────────────────────────────────

    @staticmethod
    def _derive_decision(
        request: PredictiveMaintenanceRequest,
        sensor_evals: list,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        rule_matched: bool,
    ) -> AgentDecision:
        """根据分析结果推导智能体决策。

        优先级：
        sensor_data_insufficient > critical_failure_risk
        > maintenance_work_order_required(high)
        > failure_risk_detected(medium)
        > maintenance_attention_required
        > maintenance_rule_missing > equipment_normal
        """
        # 无传感器数据
        if not sensor_evals:
            return "sensor_data_insufficient"

        # critical 风险 → 需工单 + 严重告警
        if risk.risk_level == "critical":
            return "critical_failure_risk"

        # high 风险 → 需工单
        if risk.risk_level == "high":
            return "maintenance_work_order_required"

        # medium 风险 → 故障风险
        if risk.risk_level == "medium":
            return "failure_risk_detected"

        # low 风险但有 warning 传感器
        if risk.warning_sensors:
            return "maintenance_attention_required"

        # 维护规程缺失（有故障预测类型但无匹配规程）
        if (
            failure_pred.failure_type != "no_failure_detected"
            and failure_pred.failure_type != "unknown_failure"
            and not rule_matched
            and request.maintenance_rules
        ):
            return "maintenance_rule_missing"

        # 正常
        return "equipment_normal"

    # ── 维护工单生成 ─────────────────────────────────────────

    @staticmethod
    def _generate_work_order(
        request: PredictiveMaintenanceRequest,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        time_window: TimeWindowEstimate,
        decision: str,
        nodes: list[MaintenanceNodeFeedback],
    ) -> WorkOrderSuggestion | None:
        service = PredictiveMaintenanceService()
        wo = service.generate_work_order(
            equipment=request.equipment,
            risk_assessment=risk,
            failure_prediction=failure_pred,
            time_window=time_window,
            maintenance_rules=request.maintenance_rules,
            decision=decision,
            context=request.context,
        )

        if wo is not None:
            nodes.append(
                MaintenanceNodeFeedback(
                    node="work_order_generation",
                    status="success",
                    message=(
                        f"维护工单已生成：类型={wo.work_order_type}，"
                        f"优先级={wo.priority}，"
                        f"预计工时={wo.estimated_duration_hours}h，"
                        f"窗口={wo.suggested_start_window}"
                    ),
                )
            )
        else:
            nodes.append(
                MaintenanceNodeFeedback(
                    node="work_order_generation",
                    status="success",
                    message=(
                        f"当前风险等级 {risk.risk_level} 不满足工单生成条件，"
                        "继续监控设备运行状态。"
                    ),
                )
            )

        return wo

    # ── 输出构建 ──────────────────────────────────────────────

    @staticmethod
    def _build_output(
        request: PredictiveMaintenanceRequest,
        sensor_evals: list,
        trend_results: list,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        time_window: TimeWindowEstimate,
        work_order: WorkOrderSuggestion | None,
        decision: AgentDecision,
        nodes: list[MaintenanceNodeFeedback],
    ) -> PredictiveMaintenanceOutput:
        summary = PredictiveMaintenanceAgent._build_summary(
            request, risk, failure_pred, decision
        )
        evidence = PredictiveMaintenanceAgent._build_evidence(
            request, sensor_evals, trend_results, risk, failure_pred, time_window
        )
        next_actions = PredictiveMaintenanceAgent._build_next_actions(
            decision, risk, failure_pred, work_order, request
        )

        return PredictiveMaintenanceOutput(
            summary=summary,
            decision=decision,
            evidence=evidence,
            next_actions=next_actions,
            node_feedback=nodes,
            sensor_evaluations=sensor_evals,
            trend_analyses=trend_results,
            risk_assessment=risk,
            failure_prediction=failure_pred,
            time_window=time_window,
            work_order=work_order,
        )

    @staticmethod
    def _build_summary(
        request: PredictiveMaintenanceRequest,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        decision: AgentDecision,
    ) -> str:
        eq = request.equipment
        base = (
            f"设备 {eq.equipment_id}（{eq.equipment_name}，"
            f"类型 {eq.equipment_type}）预测性维护分析完成。"
        )

        decisions_cn: dict[str, str] = {
            "equipment_normal": "所有传感器正常，设备运行状态良好。",
            "maintenance_attention_required": "传感器存在异常，需要维护关注。",
            "failure_risk_detected": "检测到故障风险，建议尽快安排检查。",
            "critical_failure_risk": "严重故障风险，需立即采取行动。",
            "maintenance_work_order_required": "已生成维护工单建议。",
            "sensor_data_insufficient": "传感器数据不足，无法完成完整分析。",
            "maintenance_rule_missing": "缺少对应的维护规程。",
        }

        detail = decisions_cn.get(decision, "")
        parts: list[str] = [base, detail]

        parts.append(
            f"风险评分 {risk.risk_score:.2f}（{risk.risk_level}），"
            f"故障类型 {failure_pred.failure_type}。"
        )

        return " ".join(parts)

    @staticmethod
    def _build_evidence(
        request: PredictiveMaintenanceRequest,
        sensor_evals: list,
        trend_results: list,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        time_window: TimeWindowEstimate,
    ) -> list[str]:
        evidence: list[str] = []

        eq = request.equipment
        evidence.append(
            f"设备 {eq.equipment_id}（{eq.equipment_type}），"
            f"状态 {eq.running_status}，"
            f"累计运行 {eq.total_runtime_hours}h"
        )
        if eq.last_maintenance_date:
            evidence.append(f"最近维护: {eq.last_maintenance_date}")

        # 设备状态说明
        if eq.running_status != "running":
            evidence.append(
                f"注意：设备当前处于 {eq.running_status} 状态，"
                "传感器异常可能因计划停机造成。"
            )

        # 维护上下文
        if request.context:
            ctx = request.context
            evidence.append(
                f"生产关键性: {ctx.production_criticality}，"
                f"备件可用: {'是' if ctx.spare_parts_available else '否'}"
            )
            if ctx.maintenance_window_hours is not None:
                evidence.append(f"可用维护窗口: {ctx.maintenance_window_hours:.1f}h")

        # 传感器证据
        critical_sensors = [e for e in sensor_evals if e.status == "critical"]
        warning_sensors = [e for e in sensor_evals if e.status == "warning"]
        if critical_sensors:
            evidence.append(
                f"严重异常传感器 ({len(critical_sensors)}): "
                + ", ".join(f"{e.sensor_type}({e.value})" for e in critical_sensors)
            )
        if warning_sensors:
            evidence.append(
                f"警告传感器 ({len(warning_sensors)}): "
                + ", ".join(f"{e.sensor_type}({e.value})" for e in warning_sensors[:5])
            )

        # 趋势证据
        alert_trends = [t for t in trend_results if t.alert]
        for t in alert_trends:
            evidence.append(
                f"趋势异常 [{t.sensor_type}]: {t.direction}，"
                f"变化 {t.change_pct:.1f}%（{t.earliest_value}→{t.latest_value}）"
            )

        # 风险评估
        evidence.append(
            f"风险评估: score={risk.risk_score:.2f}, level={risk.risk_level}"
        )

        # 故障预测
        evidence.append(
            f"故障预测: {failure_pred.failure_type}，"
            f"置信度 {failure_pred.confidence:.0%}，"
            f"来源 {failure_pred.match_source}"
        )

        # 时间窗口
        evidence.append(f"预计故障窗口: {time_window.window_description}")

        return evidence

    @staticmethod
    def _build_next_actions(
        decision: AgentDecision,
        risk: RiskAssessment,
        failure_pred: FailurePrediction,
        work_order: WorkOrderSuggestion | None,
        request: PredictiveMaintenanceRequest | None = None,
    ) -> list[str]:
        actions: list[str] = []

        if decision == "critical_failure_risk":
            actions.append("立即通知维护主管和设备操作员，准备紧急停机。")
            actions.append("安排维护人员到现场确认设备状态。")

        if decision in ("critical_failure_risk", "maintenance_work_order_required"):
            if work_order:
                actions.append(
                    f"执行维护工单：{work_order.work_order_type}，"
                    f"优先级 {work_order.priority}，"
                    f"预计工时 {work_order.estimated_duration_hours}h"
                )
                if work_order.required_parts:
                    actions.append(f"准备备件：{'、'.join(work_order.required_parts)}")

        if decision == "failure_risk_detected":
            actions.append("在 72 小时内安排设备检查与维护。")
            actions.append("加密传感器采样频率，持续监控设备状态。")

        if decision == "maintenance_attention_required":
            actions.append("记录当前传感器异常指标，纳入下次维护计划。")
            actions.append("加强巡检频次，关注异常传感器趋势变化。")

        if decision == "maintenance_rule_missing":
            actions.append(f"为故障类型 '{failure_pred.failure_type}' 补充维护规程定义。")

        if decision == "sensor_data_insufficient":
            actions.append("确认传感器连接和数据采集链路正常。")
            actions.append("补充传感器读数后重新提交分析。")

        if decision == "equipment_normal":
            actions.append("按计划执行常规维护。")
            actions.append("保持当前传感器监控频次。")

        # ── context 驱动的补充行动 ──
        if request and request.context:
            ctx = request.context
            if not ctx.spare_parts_available and work_order:
                actions.append(
                    "备件不可用：请提前协调采购备件或调用替代件。"
                )
            if (
                ctx.maintenance_window_hours is not None
                and work_order
                and ctx.maintenance_window_hours < work_order.estimated_duration_hours
            ):
                actions.append(
                    f"维护窗口不足：可用 {ctx.maintenance_window_hours:.1f}h "
                    f"< 预计工时 {work_order.estimated_duration_hours:.1f}h，"
                    "需协调延长时间或拆分作业。"
                )
            if ctx.production_criticality in ("critical", "high"):
                actions.append(
                    f"生产关键性为 {ctx.production_criticality}，"
                    "建议优先安排维护窗口以减少停机影响。"
                )

        return actions

    # ── 错误输出 ──────────────────────────────────────────────

    @staticmethod
    def _build_error_output(
        decision: AgentDecision,
        nodes: list[MaintenanceNodeFeedback],
    ) -> PredictiveMaintenanceOutput:
        nodes.append(
            MaintenanceNodeFeedback(
                node="work_order_generation",
                status="failed",
                message="输入校验失败，分析流程中止。",
            )
        )
        return PredictiveMaintenanceOutput(
            summary="传感器数据不足，无法完成预测性维护分析。",
            decision=decision,
            evidence=["输入校验失败：传感器数据为空。"],
            next_actions=[
                "确认传感器连接和数据采集链路正常。",
                "补充传感器读数后重新提交分析。",
            ],
            node_feedback=nodes,
        )

    # ── plan() 兼容 BaseAgent ─────────────────────────────────

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        return AgentResult(
            summary=f"设备预测性维护智能体已接收请求：{request_text[:80]}",
            decision="maintenance_attention_required",
            evidence=[
                "建议通过结构化接口 execute() 传入完整设备监测数据。",
            ],
            next_actions=[
                "提供设备信息（equipment）",
                "提供传感器读数列表（sensor_readings）",
                "可选：提供历史故障库（historical_failures）和维护规程（maintenance_rules）",
            ],
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
                detail=f"已识别为{self.display_name}场景，请求内容：{request_text[:60]}",
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
