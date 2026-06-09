from __future__ import annotations

from datetime import date, datetime, timezone

from app.agents.base import AgentResult, BaseAgent
from app.schemas.agent import NodeFeedback
from app.schemas.supply_chain_management import (
    AgentDecision,
    CoordinationAction,
    InventoryAssessment,
    MaterialDemand,
    PODelayRisk,
    PurchaseRecommendation,
    SupplierEvaluation,
    SupplyChainManagementOutput,
    SupplyChainManagementRequest,
    SupplyChainNodeFeedback,
    TurnoverAnalysis,
)
from app.services.supply_chain_management_service import SupplyChainManagementService

REQUIRED_NODES = [
    "input_validation",
    "material_requirement_analysis",
    "inventory_risk_evaluation",
    "shortage_risk_analysis",
    "overstock_analysis",
    "purchase_recommendation",
    "supplier_evaluation",
    "po_delivery_analysis",
    "coordination_action_generation",
    "turnover_analysis",
]


class SupplyChainManagementAgent(BaseAgent):
    """供应链协同管理智能体。

    10 节点流程：
    input_validation → material_requirement_analysis → inventory_risk_evaluation
    → shortage_risk_analysis → overstock_analysis → purchase_recommendation
    → supplier_evaluation → po_delivery_analysis
    → coordination_action_generation → turnover_analysis
    """

    name = "supply_chain_management"
    display_name = "供应链协同管理"
    scenario_hint = "供应链、库存、采购、供应商、物料、BOM、缺料、积压"

    def __init__(self) -> None:
        self.service = SupplyChainManagementService()

    def execute(self, request: SupplyChainManagementRequest) -> SupplyChainManagementOutput:
        nodes: list[SupplyChainNodeFeedback] = []

        if not self._validate_input(request, nodes):
            return self._build_error_output(nodes)

        # 1. 需求分析
        demands = self._analyze_demand(request, nodes)

        # 2. 库存评估
        assessments = self._assess_inventory(request, demands, nodes)

        # 3. 缺料
        self._analyze_shortage(assessments, nodes)

        # 4. 积压
        self._analyze_overstock(assessments, nodes)

        # 5. 供应商
        supplier_evals = self._evaluate_suppliers(request, assessments, nodes)

        # 6. 采购建议
        purchase_recs = self._recommend_purchases(request, assessments, demands, supplier_evals, nodes)

        # 7. PO 延期
        po_risks = self._analyze_po_delays(request, nodes)

        # 8. 协同行动
        coord_actions = self._generate_coordination(request, assessments, purchase_recs, po_risks, nodes)

        # 9. 周转
        turnover = self._analyze_turnover(request, demands, nodes)

        # 10. 决策
        decision = self._derive_decision(assessments, purchase_recs, po_risks, supplier_evals, request)

        return self._build_output(
            request, demands, assessments, purchase_recs, supplier_evals,
            po_risks, turnover, coord_actions, decision, nodes,
        )

    # ── 输入校验 ─────────────────────────────────────────────

    @staticmethod
    def _validate_input(request: SupplyChainManagementRequest, nodes: list) -> bool:
        issues: list[str] = []
        if not request.production_plan:
            issues.append("生产计划为空")
        if not request.inventory:
            issues.append("库存数据为空")
        if issues:
            nodes.append(SupplyChainNodeFeedback(node="input_validation", status="failed",
                                                  message="输入校验失败：" + "；".join(issues)))
            return False
        nodes.append(SupplyChainNodeFeedback(
            node="input_validation", status="success",
            message=f"输入校验通过：生产计划 {len(request.production_plan)} 条，"
                    f"BOM {len(request.bill_of_materials)} 条，库存 {len(request.inventory)} 条，"
                    f"在途PO {len(request.purchase_orders)} 条，供应商 {len(request.suppliers)} 家"
        ))
        return True

    # ── 需求分析 ─────────────────────────────────────────────

    @staticmethod
    def _analyze_demand(request, nodes) -> list[MaterialDemand]:
        svc = SupplyChainManagementService()
        demands = svc.aggregate_material_demand(request.production_plan, request.bill_of_materials)
        if not demands:
            nodes.append(SupplyChainNodeFeedback(node="material_requirement_analysis", status="warning",
                                                  message="BOM 为空，无法展开物料需求。"))
            return []
        nodes.append(SupplyChainNodeFeedback(
            node="material_requirement_analysis", status="success",
            message=f"物料需求分析完成：{len(demands)} 种物料，总需求 {sum(d.required_quantity for d in demands):.1f}"
        ))
        return demands

    # ── 库存评估 ─────────────────────────────────────────────

    @staticmethod
    def _assess_inventory(request, demands, nodes) -> list[InventoryAssessment]:
        svc = SupplyChainManagementService()
        assessments = svc.assess_inventory(
            demands, request.inventory, request.purchase_orders,
            production_plan=request.production_plan,
        )

        normal = sum(1 for a in assessments if a.status == "normal")
        shortage = sum(1 for a in assessments if a.status == "shortage")
        critical = sum(1 for a in assessments if a.status == "critical_shortage")
        overstock = sum(1 for a in assessments if a.status == "overstock")

        status = "failed" if critical > 0 else "warning" if shortage > 0 else "success"
        nodes.append(SupplyChainNodeFeedback(
            node="inventory_risk_evaluation", status=status,
            message=f"库存评估完成：{len(assessments)} 种物料，正常 {normal}，"
                    f"缺料 {shortage}，严重缺料 {critical}，积压 {overstock}"
        ))
        return assessments

    # ── 缺料风险 ─────────────────────────────────────────────

    @staticmethod
    def _analyze_shortage(assessments, nodes):
        shortages = [a for a in assessments if a.status in ("shortage", "critical_shortage")]
        criticals = [a for a in assessments if a.status == "critical_shortage"]
        if criticals:
            nodes.append(SupplyChainNodeFeedback(
                node="shortage_risk_analysis", status="failed",
                message=f"严重缺料：{len(criticals)} 种，"
                        + "、".join(f"{a.material_id}(缺{a.shortage_quantity:.1f})" for a in criticals[:5])
            ))
        elif shortages:
            nodes.append(SupplyChainNodeFeedback(
                node="shortage_risk_analysis", status="warning",
                message=f"缺料风险：{len(shortages)} 种，"
                        + "、".join(f"{a.material_id}(缺{a.shortage_quantity:.1f})" for a in shortages[:5])
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="shortage_risk_analysis", status="success",
                message="未检测到缺料风险。"
            ))

    # ── 积压分析 ─────────────────────────────────────────────

    @staticmethod
    def _analyze_overstock(assessments, nodes):
        overstocks = [a for a in assessments if a.overstock_quantity > 0]
        if overstocks:
            nodes.append(SupplyChainNodeFeedback(
                node="overstock_analysis", status="warning",
                message=f"积压风险：{len(overstocks)} 种，"
                        + "、".join(f"{a.material_id}(积压{a.overstock_quantity:.1f})" for a in overstocks[:5])
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="overstock_analysis", status="success", message="未检测到积压风险。"
            ))

    # ── 供应商评估 ───────────────────────────────────────────

    @staticmethod
    def _evaluate_suppliers(request, assessments, nodes) -> dict[str, list[SupplierEvaluation]]:
        svc = SupplyChainManagementService()
        shortage_mids = {a.material_id for a in assessments
                         if a.status in ("shortage", "critical_shortage")}
        all_evals: dict[str, list[SupplierEvaluation]] = {}
        for mid in shortage_mids:
            all_evals[mid] = svc.score_suppliers(mid, request.suppliers, request.optimization_goal)

        risk_count = sum(1 for evals in all_evals.values() for e in evals if e.risk_level != "low")
        if risk_count > 0:
            nodes.append(SupplyChainNodeFeedback(
                node="supplier_evaluation", status="warning",
                message=f"供应商评估完成：覆盖 {len(all_evals)} 种物料，{risk_count} 个供应商存在风险"
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="supplier_evaluation", status="success",
                message=f"供应商评估完成：覆盖 {len(all_evals)} 种物料。"
            ))
        return all_evals

    # ── 采购建议 ─────────────────────────────────────────────

    @staticmethod
    def _recommend_purchases(request, assessments, demands, supplier_evals, nodes) -> list[PurchaseRecommendation]:
        svc = SupplyChainManagementService()
        recs = svc.generate_purchase_recommendations(
            assessments, demands, request.suppliers, request.inventory, request.optimization_goal
        )
        if recs:
            nodes.append(SupplyChainNodeFeedback(
                node="purchase_recommendation", status="success",
                message=f"已生成 {len(recs)} 条采购建议，总预计成本 {sum(r.estimated_cost for r in recs):.2f}"
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="purchase_recommendation", status="success",
                message="当前无需采购建议。"
            ))
        return recs

    # ── PO 延期 ──────────────────────────────────────────────

    @staticmethod
    def _analyze_po_delays(request, nodes) -> list[PODelayRisk]:
        svc = SupplyChainManagementService()
        risks = svc.analyze_po_delay_risks(request.purchase_orders)
        if risks:
            high = [r for r in risks if r.risk_level == "high"]
            nodes.append(SupplyChainNodeFeedback(
                node="po_delivery_analysis",
                status="warning" if high else "success",
                message=f"PO 延期分析：{len(risks)} 个采购单延期，高风险 {len(high)} 个"
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="po_delivery_analysis", status="success", message="在途采购单均按期。"
            ))
        return risks

    # ── 协同行动 ─────────────────────────────────────────────

    @staticmethod
    def _generate_coordination(request, assessments, purchase_recs, po_risks, nodes) -> list[CoordinationAction]:
        svc = SupplyChainManagementService()
        actions = svc.generate_coordination_actions(assessments, purchase_recs, po_risks)
        if actions:
            nodes.append(SupplyChainNodeFeedback(
                node="coordination_action_generation", status="success",
                message=f"已生成 {len(actions)} 条协同行动建议"
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="coordination_action_generation", status="success",
                message="当前无需协同行动。"
            ))
        return actions

    # ── 周转分析 ─────────────────────────────────────────────

    @staticmethod
    def _analyze_turnover(request, demands, nodes) -> list[TurnoverAnalysis]:
        svc = SupplyChainManagementService()
        results = svc.analyze_turnover(demands, request.inventory)
        low = [t for t in results if "积压" in t.assessment or "偏低" in t.assessment or "无有效" in t.assessment]
        if low:
            nodes.append(SupplyChainNodeFeedback(
                node="turnover_analysis", status="warning",
                message=f"周转分析：{len(low)} 种物料周转率异常，"
                        + "、".join(f"{t.material_id}({t.turnover_rate:.1f})" for t in low[:5])
            ))
        else:
            nodes.append(SupplyChainNodeFeedback(
                node="turnover_analysis", status="success",
                message=f"周转分析完成：{len(results)} 种物料。"
            ))
        return results

    # ── 决策 ─────────────────────────────────────────────────

    @staticmethod
    def _derive_decision(assessments, purchase_recs, po_risks, supplier_evals, request) -> AgentDecision:
        if not assessments:
            if not request.bill_of_materials:
                return "data_insufficient"

        # 供应商风险 — 缺料物料对应供应商中存在 risk_level=="high" 时触发
        has_shortage = any(
            a.status in ("shortage", "critical_shortage") for a in assessments
        )
        if has_shortage:
            for evals in supplier_evals.values():
                if any(e.risk_level == "high" for e in evals):
                    return "supplier_risk_detected"

        if any(a.status == "critical_shortage" for a in assessments):
            return "critical_shortage"

        # 供应商风险（有缺料且供应商不可靠 medium+）
        for evals in supplier_evals.values():
            if any(e.risk_level != "low" for e in evals):
                if any(a.status == "shortage" for a in assessments):
                    return "supplier_risk_detected"

        if any(a.status == "shortage" for a in assessments):
            return "purchase_recommended" if purchase_recs else "shortage_risk_detected"

        if purchase_recs:
            return "purchase_recommended"

        if any(a.overstock_quantity > 0 for a in assessments):
            return "overstock_risk_detected"

        if po_risks:
            return "po_delay_risk"

        return "supply_chain_stable"

    # ── 输出 ─────────────────────────────────────────────────

    @staticmethod
    def _build_output(request, demands, assessments, purchase_recs, supplier_evals,
                      po_risks, turnover, coord_actions, decision, nodes):
        all_evals: list[SupplierEvaluation] = []
        for ev in supplier_evals.values():
            all_evals.extend(ev)

        return SupplyChainManagementOutput(
            summary=SupplyChainManagementAgent._summary(request, assessments, purchase_recs, decision),
            decision=decision,
            evidence=SupplyChainManagementAgent._evidence(request, demands, assessments, purchase_recs, po_risks),
            next_actions=SupplyChainManagementAgent._next_actions(decision, assessments, purchase_recs, po_risks),
            node_feedback=nodes,
            material_demands=demands,
            inventory_assessments=assessments,
            purchase_recommendations=purchase_recs,
            supplier_evaluations=all_evals,
            po_delay_risks=po_risks,
            turnover_analyses=turnover,
            coordination_actions=coord_actions,
        )

    @staticmethod
    def _summary(request, assessments, purchase_recs, decision):
        dc = {
            "supply_chain_stable": "供应链状态稳定。",
            "shortage_risk_detected": "检测到缺料风险。",
            "critical_shortage": "严重缺料，需立即采购。",
            "purchase_recommended": "已生成采购建议。",
            "overstock_risk_detected": "检测到库存积压。",
            "supplier_risk_detected": "部分供应商存在风险。",
            "po_delay_risk": "在途采购单延期。",
            "data_insufficient": "数据不足。",
        }
        base = f"生产计划 {len(request.production_plan)} 条，{len(assessments)} 种物料。"
        parts = [base, dc.get(decision, "")]
        if purchase_recs:
            parts.append(f"采购建议 {len(purchase_recs)} 条，总成本 {sum(r.estimated_cost for r in purchase_recs):.2f}。")
        return " ".join(parts)

    @staticmethod
    def _evidence(request, demands, assessments, purchase_recs, po_risks):
        ev: list[str] = []
        ev.append(f"生产计划 {len(request.production_plan)} 条，物料需求 {len(demands)} 种")
        for a in assessments:
            if a.status in ("shortage", "critical_shortage"):
                ev.append(f"[{a.status}] {a.material_id}: 需求 {a.required_quantity:.1f}，可用 {a.projected_available:.1f}，缺口 {a.shortage_quantity:.1f}")
        for a in assessments:
            if a.overstock_quantity > 0:
                ev.append(f"[overstock] {a.material_id}: 可用 {a.useable_quantity:.1f}，max_stock {a.max_stock}")
        for r in purchase_recs[:5]:
            ev.append(f"[purchase] {r.material_id}: {r.recommended_quantity:.1f}，供应商 {r.recommended_supplier_name}，成本 {r.estimated_cost:.2f}")
        for pr in po_risks[:5]:
            ev.append(f"[po_delay] {pr.po_id}: {pr.impact}")
        return ev

    @staticmethod
    def _next_actions(decision, assessments, purchase_recs, po_risks):
        actions: list[str] = []
        if decision == "critical_shortage":
            actions.append("立即启动紧急采购流程。")
            for a in assessments:
                if a.status == "critical_shortage":
                    actions.append(f"紧急采购 {a.material_id}，缺口 {a.shortage_quantity:.1f}。")
        if decision in ("shortage_risk_detected", "purchase_recommended"):
            actions.append("按采购建议生成采购单并提交审批。")
            for r in purchase_recs[:3]:
                actions.append(f"采购 {r.material_id}: {r.recommended_quantity:.1f}，供应商 {r.recommended_supplier_name}")
        if decision == "overstock_risk_detected":
            actions.append("调整后续采购计划，减少积压物料的采购量。")
        if decision == "supplier_risk_detected":
            actions.append("审查高风险供应商的交货与质量表现。")
            actions.append("评估启用替代供应商的可能性。")
        if decision == "po_delay_risk":
            for pr in po_risks[:3]:
                actions.append(f"跟进延期采购单 {pr.po_id}，与供应商确认最新交期。")
        if decision == "supply_chain_stable":
            actions.append("按计划执行采购与库存管理。")
        if decision == "data_insufficient":
            actions.append("补充完整的 BOM 和库存数据后重新提交分析。")
        return actions

    @staticmethod
    def _build_error_output(nodes) -> SupplyChainManagementOutput:
        nodes.append(SupplyChainNodeFeedback(node="coordination_action_generation", status="failed",
                                              message="输入校验失败，分析流程中止。"))
        return SupplyChainManagementOutput(
            summary="输入数据不完整，供应链分析流程中止。",
            decision="data_insufficient",
            evidence=["输入校验失败：生产计划或库存数据为空。"],
            next_actions=["补充生产计划和库存数据后重新提交分析。"],
            node_feedback=nodes,
        )

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        return AgentResult(summary=f"供应链管理智能体已接收请求：{request_text[:80]}",
                           decision="supply_chain_stable",
                           evidence=["建议通过结构化接口 execute() 传入完整供应链数据。"],
                           next_actions=["提供生产计划、BOM、库存数据。"])

    def build_node_feedback(self, request_text: str, result: AgentResult) -> list[NodeFeedback]:
        now = datetime.now(tz=timezone.utc)
        return [
            NodeFeedback(node_id=f"{self.name}-intent", node_name="意图识别", status="completed",
                         detail=f"已识别为{self.display_name}场景", started_at=now, completed_at=now),
            NodeFeedback(node_id=f"{self.name}-analysis", node_name="规则分析", status="completed",
                         detail=result.summary, started_at=now, completed_at=now),
            NodeFeedback(node_id=f"{self.name}-decision", node_name="决策输出", status="completed",
                         detail=result.decision, started_at=now, completed_at=now),
        ]
