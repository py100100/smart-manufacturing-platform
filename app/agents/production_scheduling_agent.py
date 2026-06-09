from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentResult, BaseAgent
from app.schemas.agent import NodeFeedback
from app.schemas.production_scheduling import (
    SchedulingAgentOutput,
    SchedulingRequest,
    SchedulingResult,
)
from app.services.production_scheduling_service import ProductionSchedulingService


class ProductionSchedulingAgent(BaseAgent):
    """生产调度优化智能体。

    职责：编排调度决策流程，调用 service 完成产能评估、排程计算和瓶颈分析，
    输出标准化的 AgentResult 与节点反馈。
    """

    name = "production_scheduling"
    display_name = "生产调度优化"
    scenario_hint = "排产、工单、交期、产能、瓶颈、设备、工艺路线"

    def __init__(self) -> None:
        self.service = ProductionSchedulingService()

    # ── 主入口 ────────────────────────────────────────────────

    def execute(self, request: SchedulingRequest) -> SchedulingAgentOutput:
        """执行生产调度决策全流程。"""
        nodes: list[NodeFeedback] = []

        # 1. 输入校验
        validation_ok = self._validate_input(request, nodes)
        if not validation_ok:
            return self._build_error_output("input_invalid", nodes)

        # 2. 订单排序
        self._prioritize_orders(request, nodes)

        # 3. 工艺路线匹配
        route_issues = self._match_routes(request, nodes)

        # 4. 设备能力评估与排程
        scheduling_result = self._evaluate_and_schedule(request, nodes)

        # 5. 瓶颈分析（已含在 scheduling_result 中，此处追加反馈）
        self._analyze_bottlenecks(scheduling_result, nodes)

        # 6. 汇总
        return self._build_output(request, scheduling_result, route_issues, nodes)

    # ── 步骤实现 ──────────────────────────────────────────────

    def _validate_input(self, request: SchedulingRequest, nodes: list[NodeFeedback]) -> bool:
        now = datetime.now(tz=timezone.utc)
        hard_issues: list[str] = []
        soft_issues: list[str] = []

        if not request.orders:
            hard_issues.append("订单列表为空")
        if not request.work_orders:
            hard_issues.append("工单列表为空")
        if not request.process_routes:
            hard_issues.append("工艺路线列表为空")
        if not request.equipment:
            hard_issues.append("设备列表为空")

        # 校验工单与订单的引用完整性（硬失败）
        order_ids = {o.order_id for o in request.orders}
        for wo in request.work_orders:
            if wo.order_id not in order_ids:
                hard_issues.append(f"工单 {wo.work_order_id} 引用的订单 {wo.order_id} 不存在")

        # 校验产品在工艺路线中是否存在（仅提醒，不阻断流程——由 route_matching 阶段处理）
        if request.process_routes:
            product_ids = {r.product_id for r in request.process_routes}
            missing = [o.product_id for o in request.orders if o.product_id not in product_ids]
            if missing:
                soft_issues.append(
                    f"产品 {', '.join(missing)} 在工艺路线中未匹配，"
                    "将在后续步骤处理"
                )

        has_hard_error = len(hard_issues) > 0
        status = "failed" if has_hard_error else "completed"
        all_issues = hard_issues + soft_issues
        detail = "订单、工单、设备、工艺路线输入完整" if not all_issues else "; ".join(all_issues)

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-input_validation",
                node_name="输入校验",
                status=status,
                detail=detail,
                started_at=now,
                completed_at=now,
            )
        )
        return not has_hard_error

    def _prioritize_orders(self, request: SchedulingRequest, nodes: list[NodeFeedback]) -> None:
        now = datetime.now(tz=timezone.utc)
        sorted_orders = self.service.sort_orders(request.orders, request.optimization_goal)
        high_count = sum(1 for o in sorted_orders if o.priority == "high")
        medium_count = sum(1 for o in sorted_orders if o.priority == "medium")
        low_count = sum(1 for o in sorted_orders if o.priority == "low")

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-order_prioritization",
                node_name="订单优先级排序",
                status="completed",
                detail=(
                    f"已按 {request.optimization_goal} 策略排序 "
                    f"（高:{high_count} 中:{medium_count} 低:{low_count}）"
                ),
                started_at=now,
                completed_at=now,
            )
        )

    def _match_routes(self, request: SchedulingRequest, nodes: list[NodeFeedback]) -> set[str]:
        """返回存在工艺路线缺失的 product_id 集合。"""
        now = datetime.now(tz=timezone.utc)
        missing_products: set[str] = set()
        matched: list[str] = []

        for order in request.orders:
            route = self.service.match_process_route(order.product_id, request.process_routes)
            if route is None:
                missing_products.add(order.product_id)
            else:
                matched.append(f"{order.product_id}({route.route_id})")

        if missing_products:
            status = "completed"
            detail = (
                f"已匹配: {', '.join(matched)}；"
                f"缺失工艺路线产品: {', '.join(sorted(missing_products))}"
            )
        else:
            status = "completed"
            detail = f"已匹配全部产品的工艺路线: {', '.join(matched)}"

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-route_matching",
                node_name="工艺路线匹配",
                status=status,
                detail=detail,
                started_at=now,
                completed_at=now,
            )
        )
        return missing_products

    def _evaluate_and_schedule(
        self, request: SchedulingRequest, nodes: list[NodeFeedback]
    ) -> SchedulingResult:
        now = datetime.now(tz=timezone.utc)
        result = self.service.generate_schedule(request)

        scheduled = sum(1 for s in result.schedule if s.status == "scheduled")
        risk = sum(1 for s in result.schedule if s.status == "capacity_risk")
        unavailable = sum(1 for s in result.schedule if s.status == "unavailable")
        delayed = sum(1 for s in result.schedule if s.status == "delayed")

        if risk > 0 or unavailable > 0:
            status = "completed"
        else:
            status = "completed"

        detail = (
            f"排程完成: {scheduled} 正常, {risk} 产能风险, "
            f"{unavailable} 不可用, {delayed} 延期"
        )

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-capacity_evaluation",
                node_name="产能评估与排程",
                status=status,
                detail=detail,
                started_at=now,
                completed_at=now,
            )
        )
        return result

    def _analyze_bottlenecks(
        self, result: SchedulingResult, nodes: list[NodeFeedback]
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        critical = [b for b in result.bottlenecks if b.severity == "critical"]
        warnings = [b for b in result.bottlenecks if b.severity == "warning"]

        if critical:
            status = "completed"
            detail = (
                f"发现 {len(critical)} 个严重瓶颈: "
                + "; ".join(
                    f"{b.equipment_name}({b.utilization}%)" for b in critical[:3]
                )
            )
        elif warnings:
            status = "completed"
            detail = (
                f"发现 {len(warnings)} 个设备接近瓶颈: "
                + "; ".join(
                    f"{b.equipment_name}({b.utilization}%)" for b in warnings[:3]
                )
            )
        else:
            status = "completed"
            detail = f"所有 {len(result.bottlenecks)} 台设备负载正常"

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-bottleneck_analysis",
                node_name="瓶颈分析",
                status=status,
                detail=detail,
                started_at=now,
                completed_at=now,
            )
        )

    # ── 输出构建 ──────────────────────────────────────────────

    def _build_output(
        self,
        request: SchedulingRequest,
        result: SchedulingResult,
        route_issues: set[str],
        nodes: list[NodeFeedback],
    ) -> SchedulingAgentOutput:
        now = datetime.now(tz=timezone.utc)

        # 推导 decision
        decision = self._derive_decision(result, route_issues)

        # 构建 summary
        summary = self._build_summary(result, decision)

        # 构建 evidence
        evidence = self._build_evidence(result, route_issues, request)

        # 构建 next_actions
        next_actions = self._build_next_actions(result, decision, route_issues)

        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-schedule_generation",
                node_name="调度建议生成",
                status="completed",
                detail=f"决策: {decision}；{summary}",
                started_at=now,
                completed_at=now,
            )
        )

        return SchedulingAgentOutput(
            summary=summary,
            decision=decision,
            evidence=evidence,
            next_actions=next_actions,
            node_feedback=nodes,
            schedule_detail=result,
        )

    # ── plan() 兼容 BaseAgent ─────────────────────────────────

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        """BaseAgent 兼容入口。优先使用 execute() 处理结构化输入。"""
        return AgentResult(
            summary=f"生产调度智能体已接收请求：{request_text[:80]}",
            decision="schedule_risk_detected",
            evidence=["建议通过结构化接口 execute() 传入完整订单和工单数据进行排程。"],
            next_actions=[
                "提供订单列表（orders）",
                "提供工单列表（work_orders）",
                "提供工艺路线（process_routes）",
                "提供设备清单（equipment）",
            ],
        )

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _derive_decision(result: SchedulingResult, route_issues: set[str]) -> str:
        """从调度结果推导智能体决策。"""
        # 检查是否有工艺路线缺失
        has_route_missing = any(
            s.status == "unavailable" and "无匹配工艺路线" in s.status_reason
            for s in result.schedule
        )
        # 检查是否有设备不可用
        has_machine_unavailable = any(
            s.status == "unavailable" and "无可用设备" in s.status_reason
            for s in result.schedule
        )

        if has_route_missing and not has_machine_unavailable:
            return "route_missing"
        if has_machine_unavailable:
            return "machine_unavailable"
        if result.overall_feasibility == "feasible":
            return "schedule_approved"
        if result.overall_feasibility == "infeasible":
            return "capacity_insufficient"
        return "schedule_risk_detected"

    @staticmethod
    def _build_summary(result: SchedulingResult, decision: str) -> str:
        decisions_cn = {
            "schedule_approved": "所有订单可正常排产。",
            "schedule_risk_detected": "部分订单存在排产风险，需调整资源或交期。",
            "capacity_insufficient": "当前产能不足以完成全部订单，建议调整交期或增加产能。",
            "route_missing": "存在产品无匹配工艺路线，请补充工艺路线后再排产。",
            "machine_unavailable": "存在工序无可用设备，请检查设备状态。",
        }
        base = decisions_cn.get(decision, "调度完成。")
        return (
            f"{base} 共 {result.total_orders} 个订单，"
            f"{result.scheduled_orders} 个可按时交付，"
            f"{result.delayed_orders} 个存在风险。"
        )

    @staticmethod
    def _build_evidence(
        result: SchedulingResult, route_issues: set[str], request: SchedulingRequest
    ) -> list[str]:
        evidence: list[str] = []

        # 订单概览
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        for order in request.orders:
            priority_counts[order.priority] += 1
        evidence.append(
            f"订单总数 {result.total_orders}"
            f"（高:{priority_counts['high']} "
            f"中:{priority_counts['medium']} "
            f"低:{priority_counts['low']}）"
        )

        # 工艺路线匹配情况
        if route_issues:
            evidence.append(f"工艺路线缺失产品: {', '.join(sorted(route_issues))}")
        else:
            evidence.append("所有产品均匹配到工艺路线。")

        # 瓶颈设备
        for b in result.bottlenecks:
            if b.severity in ("critical", "warning"):
                evidence.append(
                    f"瓶颈设备 {b.equipment_name}: "
                    f"负载 {b.total_load_minutes:.0f} 分钟, "
                    f"利用率 {b.utilization}%"
                )

        # 产能风险项
        risk_items = [s for s in result.schedule if s.status != "scheduled"]
        for item in risk_items[:5]:
            evidence.append(f"[{item.status}] {item.step_name}: {item.status_reason}")

        return evidence

    @staticmethod
    def _build_next_actions(
        result: SchedulingResult, decision: str, route_issues: set[str]
    ) -> list[str]:
        actions: list[str] = []

        if route_issues:
            for pid in sorted(route_issues):
                actions.append(f"为产品 {pid} 补充工艺路线定义。")

        if decision == "capacity_insufficient":
            for b in result.bottlenecks:
                if b.severity == "critical":
                    actions.append(
                        f"为瓶颈设备 {b.equipment_name} 增加工时或启用替代设备。"
                    )
            actions.append("评估是否可以调整交期或拆分工单。")

        if decision == "machine_unavailable":
            actions.append("检查设备状态，确认维护/离线设备是否可恢复。")

        if decision == "schedule_risk_detected":
            for b in result.bottlenecks:
                if b.severity == "critical":
                    actions.append(
                        f"建议对 {b.equipment_name} 进行负载分流。"
                    )
            actions.append("优先锁定高风险订单的交期调整方案。")

        if decision == "schedule_approved":
            actions.append("按生成的排程计划下发工单到车间。")
            actions.append("监控瓶颈设备利用率变化。")

        # 物料相关
        if result.delayed_orders > 0:
            actions.append("核实延期订单的物料库存与采购在途。")

        return actions

    def _build_error_output(
        self, error_type: str, nodes: list[NodeFeedback]
    ) -> SchedulingAgentOutput:
        """当输入校验失败时返回错误输出。"""
        now = datetime.now(tz=timezone.utc)
        nodes.append(
            NodeFeedback(
                node_id="production_scheduling-schedule_generation",
                node_name="调度建议生成",
                status="failed",
                detail="输入校验失败，调度流程中止。",
                started_at=now,
                completed_at=now,
            )
        )
        return SchedulingAgentOutput(
            summary="输入数据不完整或格式不正确，调度流程中止。",
            decision="route_missing",
            evidence=["输入校验失败，请检查必填字段。"],
            next_actions=["补充完整的订单、工单、设备、工艺路线数据后重试。"],
            node_feedback=nodes,
            schedule_detail=SchedulingResult(overall_feasibility="infeasible"),
        )
