from __future__ import annotations

from datetime import date

from app.schemas.supply_chain_management import (
    BOMEntry,
    CoordinationAction,
    InventoryAssessment,
    InventoryItem,
    MaterialDemand,
    PODelayRisk,
    ProductionPlanItem,
    PurchaseOrderItem,
    PurchaseRecommendation,
    SupplierEvaluation,
    SupplierInfo,
    TurnoverAnalysis,
)

BALANCED_WEIGHTS = {"on_time": 0.4, "quality": 0.3, "price": 0.2, "risk": 0.1}
SUPPLIER_RISK_THRESHOLDS = [(0.4, "high"), (0.7, "medium")]
RISK_ADJUSTMENT: dict[str, float] = {"low": 1.0, "medium": 0.6, "high": 0.2}


class SupplyChainManagementService:
    """供应链协同管理核心业务服务。"""

    # ── RAG 预留接口 ──────────────────────────────────────────

    @staticmethod
    def match_supplier_for_material(
        material_id: str, suppliers: list[SupplierInfo]
    ) -> list[SupplierInfo]:
        return [s for s in suppliers if material_id in s.material_ids and s.status == "active"]

    @staticmethod
    def match_bom_for_product(
        product_id: str, bill_of_materials: list[BOMEntry]
    ) -> list[BOMEntry]:
        return [b for b in bill_of_materials if b.product_id == product_id]

    # ── 物料需求汇总（BOM 展开 — 嵌套结构） ──────────────────

    @staticmethod
    def aggregate_material_demand(
        production_plan: list[ProductionPlanItem],
        bill_of_materials: list[BOMEntry],
    ) -> list[MaterialDemand]:
        """根据生产计划 × BOM 展开物料总需求。

        BOM 为嵌套结构：BOMEntry.product_id → .materials[]，
        每个子物料有 required_quantity_per_unit。
        """
        demand_map: dict[str, MaterialDemand] = {}

        for plan in production_plan:
            bom_entries = SupplyChainManagementService.match_bom_for_product(
                plan.product_id, bill_of_materials
            )
            for bom in bom_entries:
                for mat in bom.materials:
                    mid = mat.material_id
                    required = plan.quantity * mat.required_quantity_per_unit
                    if mid not in demand_map:
                        demand_map[mid] = MaterialDemand(
                            material_id=mid,
                            material_name=mat.material_name,
                            required_quantity=0.0,
                            unit=mat.unit,
                            source_plans=[],
                        )
                    demand_map[mid].required_quantity += required
                    if plan.plan_id not in demand_map[mid].source_plans:
                        demand_map[mid].source_plans.append(plan.plan_id)

        return sorted(demand_map.values(), key=lambda d: d.material_id)

    # ── 库存评估 ──────────────────────────────────────────────

    @staticmethod
    def assess_inventory(
        demands: list[MaterialDemand],
        inventory: list[InventoryItem],
        purchase_orders: list[PurchaseOrderItem],
        production_plan: list[ProductionPlanItem] | None = None,
        analysis_date: date | None = None,
    ) -> list[InventoryAssessment]:
        """评估每个物料的库存状态。

        useable_quantity = available_quantity - reserved
        projected_available = useable + in_transit_on_time（按期在途）
        在途按期条件：status in ("confirmed", "in_transit")
                     且 expected_arrival_date <= earliest_plan_start_date
        缺料公式：shortage = max(0, required + safety_stock - projected)
        缺料等级：
          shortage <= 0                                  → normal
          0 < shortage <= required * 0.2                 → shortage
          shortage > required * 0.2                      → critical_shortage
        积压：useable > max_stock（仅当 max_stock 不为 None 且无缺料）。
        """
        inv_map = {i.material_id: i for i in inventory}

        # 生产计划最早开工日
        earliest_start: date | None = None
        if production_plan:
            for plan in production_plan:
                sd = plan.start_date
                if isinstance(sd, str):
                    sd = date.fromisoformat(sd)
                if isinstance(sd, date):
                    if earliest_start is None or sd < earliest_start:
                        earliest_start = sd
        if earliest_start is None:
            earliest_start = analysis_date or date.today()

        results: list[InventoryAssessment] = []

        for demand in demands:
            inv = inv_map.get(demand.material_id)
            available = inv.available_quantity if inv else 0.0
            reserved = inv.reserved if inv else 0.0
            safety = inv.safety_stock if inv else 0.0
            max_stk = inv.max_stock if inv else None

            useable = max(0.0, available - reserved)

            # 在途按期到货量：
            # status in ("confirmed", "in_transit")
            # AND expected_arrival_date <= earliest_plan_start_date
            in_transit_on_time = 0.0
            for po in purchase_orders:
                if po.material_id != demand.material_id:
                    continue
                if po.status not in ("confirmed", "in_transit"):
                    continue
                edd = po.expected_delivery_date
                if isinstance(edd, str):
                    edd = date.fromisoformat(edd)
                if isinstance(edd, date) and edd > earliest_start:
                    continue  # 预计到货晚于最早开工日 → 不计入
                remaining = max(0.0, po.order_quantity - po.received_quantity)
                in_transit_on_time += remaining

            projected = useable + in_transit_on_time
            required = demand.required_quantity

            # 任务书公式：shortage = max(0, required + safety_stock - projected)
            shortage_qty = max(0.0, required + safety - projected)

            # 缺料等级（任务书规则）
            if required > 0:
                if shortage_qty <= 0:
                    status = "normal"
                elif shortage_qty <= required * 0.2:
                    status = "shortage"
                else:
                    status = "critical_shortage"
            else:
                status = "normal"

            # 积压判断：useable > max_stock（无缺料时）
            overstock_qty = 0.0
            if max_stk is not None and shortage_qty <= 0 and useable > max_stk:
                overstock_qty = useable - max_stk
                if status == "normal":
                    status = "overstock"

            turnover = 0.0
            if useable > 0 and required > 0:
                turnover = required / useable

            results.append(
                InventoryAssessment(
                    material_id=demand.material_id,
                    available_quantity=available,
                    reserved=reserved,
                    useable_quantity=useable,
                    safety_stock=safety,
                    in_transit_on_time=in_transit_on_time,
                    projected_available=projected,
                    required_quantity=required,
                    shortage_quantity=shortage_qty,
                    overstock_quantity=overstock_qty,
                    max_stock=max_stk,
                    turnover_rate=round(turnover, 2),
                    status=status,
                )
            )

        return results

    # ── 供应商评分 ────────────────────────────────────────────

    @staticmethod
    def score_suppliers(
        material_id: str,
        suppliers: list[SupplierInfo],
        optimization_goal: str = "delivery_first",
    ) -> list[SupplierEvaluation]:
        active = SupplyChainManagementService.match_supplier_for_material(
            material_id, suppliers
        )
        if not active:
            return []

        evaluations: list[SupplierEvaluation] = []
        # 价格归一化（备选：当 price_score 未提供时从 unit_price 推算）
        prices = [s.unit_price for s in active if s.unit_price > 0]
        min_price = min(prices) if prices else 1.0

        for s in active:
            on_time = s.on_time_delivery_rate
            quality = s.quality_pass_rate

            # price_score 优先，否则从 unit_price 归一化
            if s.price_score > 0:
                price_val = s.price_score
            elif s.unit_price > 0:
                price_val = min_price / s.unit_price
            else:
                price_val = 1.0

            risk_adj = RISK_ADJUSTMENT.get(s.risk_level, 1.0)

            if optimization_goal == "delivery_first":
                composite = on_time
            else:
                composite = (
                    on_time * BALANCED_WEIGHTS["on_time"]
                    + quality * BALANCED_WEIGHTS["quality"]
                    + price_val * BALANCED_WEIGHTS["price"]
                    + risk_adj * BALANCED_WEIGHTS["risk"]
                )

            # 风险等级：输入 risk_level=="high" 直接保留，不被高分覆盖
            if s.risk_level == "high":
                risk = "high"
            else:
                risk = "low"
                for threshold, level in SUPPLIER_RISK_THRESHOLDS:
                    if composite < threshold:
                        risk = level
                        break

            recommendation = "not_recommended"
            if composite >= 0.7:
                recommendation = "recommended"
            elif composite >= 0.4:
                recommendation = "alternative"

            evaluations.append(
                SupplierEvaluation(
                    supplier_id=s.supplier_id,
                    supplier_name=s.supplier_name,
                    on_time_rate=on_time,
                    quality_rate=quality,
                    lead_time_days=s.lead_time_days,
                    unit_price=s.unit_price if s.unit_price > 0 else price_val,
                    composite_score=round(composite, 4),
                    risk_level=risk,
                    recommendation=recommendation,
                )
            )

        evaluations.sort(key=lambda e: e.composite_score, reverse=True)
        return evaluations

    # ── 采购建议生成 ──────────────────────────────────────────

    @staticmethod
    def generate_purchase_recommendations(
        assessments: list[InventoryAssessment],
        demands: list[MaterialDemand],
        suppliers: list[SupplierInfo],
        inventory: list[InventoryItem],
        optimization_goal: str = "delivery_first",
    ) -> list[PurchaseRecommendation]:
        demand_map = {d.material_id: d for d in demands}
        recommendations: list[PurchaseRecommendation] = []

        for a in assessments:
            if a.shortage_quantity <= 0:
                continue

            demand = demand_map.get(a.material_id)
            name = demand.material_name if demand else a.material_id

            evals = SupplyChainManagementService.score_suppliers(
                a.material_id, suppliers, optimization_goal
            )
            best = evals[0] if evals else None
            inv = next((i for i in inventory if i.material_id == a.material_id), None)

            urgency: str = "urgent" if a.status == "critical_shortage" else "high"

            recommendations.append(
                PurchaseRecommendation(
                    material_id=a.material_id,
                    material_name=name,
                    recommended_quantity=a.shortage_quantity,
                    recommended_supplier_id=best.supplier_id if best else "",
                    recommended_supplier_name=best.supplier_name if best else "",
                    unit_price=best.unit_price if best else 0.0,
                    estimated_cost=a.shortage_quantity * best.unit_price if best else 0.0,
                    lead_time_days=best.lead_time_days if best else (inv.lead_time_days if inv else 0),
                    urgency=urgency,
                    reason=(
                        f"物料 {name} 缺料 {a.shortage_quantity:.1f}，"
                        f"可用 {a.useable_quantity:.1f}，安全库存 {a.safety_stock:.1f}"
                    ),
                )
            )

        return recommendations

    # ── 采购单延期风险 ────────────────────────────────────────

    @staticmethod
    def analyze_po_delay_risks(
        purchase_orders: list[PurchaseOrderItem],
        analysis_date: date | None = None,
    ) -> list[PODelayRisk]:
        today = analysis_date or date.today()
        risks: list[PODelayRisk] = []

        for po in purchase_orders:
            edd = po.expected_delivery_date
            if isinstance(edd, str):
                edd = date.fromisoformat(edd)

            if po.status == "delayed":
                delay = max(0, (today - edd).days) if isinstance(edd, date) else 0
                risk_level = "high" if delay > 7 else "medium" if delay > 3 else "low"
                risks.append(
                    PODelayRisk(
                        po_id=po.po_id, material_id=po.material_id,
                        supplier_id=po.supplier_id,
                        expected_delivery_date=str(edd), status="delayed",
                        delay_days=delay, risk_level=risk_level,
                        impact=(
                            f"物料 {po.material_id} 延期 {delay} 天，"
                            f"缺料 {po.order_quantity - po.received_quantity:.1f} 单位"
                        ),
                    )
                )
            elif po.status in ("in_transit", "confirmed") and isinstance(edd, date) and edd < today:
                delay = (today - edd).days
                risk_level = "high" if delay > 7 else "medium" if delay > 3 else "low"
                risks.append(
                    PODelayRisk(
                        po_id=po.po_id, material_id=po.material_id,
                        supplier_id=po.supplier_id,
                        expected_delivery_date=str(edd), status="in_transit_overdue",
                        delay_days=delay, risk_level=risk_level,
                        impact=(
                            f"物料 {po.material_id} 已逾期 {delay} 天，"
                            f"待收货 {po.order_quantity - po.received_quantity:.1f} 单位"
                        ),
                    )
                )

        risks.sort(key=lambda r: r.delay_days, reverse=True)
        return risks

    # ── 库存周转分析 ──────────────────────────────────────────

    @staticmethod
    def analyze_turnover(
        demands: list[MaterialDemand],
        inventory: list[InventoryItem],
    ) -> list[TurnoverAnalysis]:
        inv_map = {i.material_id: i for i in inventory}
        results: list[TurnoverAnalysis] = []

        for demand in demands:
            inv = inv_map.get(demand.material_id)
            useable = max(0.0, (inv.available_quantity - inv.reserved)) if inv else 0.0
            annual_demand = demand.required_quantity * 12
            if useable <= 0:
                turnover_rate = 0.0
                turnover_days = 999.0
                assessment = "无有效周转数据 — 可用库存为零"
            else:
                turnover_rate = annual_demand / useable
                turnover_days = 365.0 / turnover_rate if turnover_rate > 0 else 999.0
                if turnover_rate >= 6:
                    assessment = "健康 — 周转率良好"
                elif turnover_rate >= 3:
                    assessment = "偏低 — 建议关注库存水平"
                elif turnover_rate > 0:
                    assessment = "偏高 — 库存积压风险"
                else:
                    assessment = "无有效周转数据"

            results.append(
                TurnoverAnalysis(
                    material_id=demand.material_id,
                    annual_demand=round(annual_demand, 1),
                    average_inventory=round(useable, 1),
                    turnover_rate=round(turnover_rate, 2),
                    turnover_days=round(turnover_days, 1),
                    assessment=assessment,
                )
            )

        return results

    # ── 协同行动生成 ──────────────────────────────────────────

    @staticmethod
    def generate_coordination_actions(
        assessments: list[InventoryAssessment],
        purchase_recs: list[PurchaseRecommendation],
        po_risks: list[PODelayRisk],
    ) -> list[CoordinationAction]:
        """基于缺料、积压、延期生成上下游协同行动建议。"""
        actions: list[CoordinationAction] = []

        for a in assessments:
            if a.status == "critical_shortage":
                actions.append(
                    CoordinationAction(
                        action_type="expedite",
                        material_id=a.material_id,
                        from_source="供应商",
                        to_target="产线",
                        quantity=a.shortage_quantity,
                        suggested_timing="立即",
                        reason=f"严重缺料 {a.shortage_quantity:.1f}，需紧急催货或调配。",
                    )
                )
            elif a.status == "shortage":
                actions.append(
                    CoordinationAction(
                        action_type="purchase",
                        material_id=a.material_id,
                        from_source="供应商",
                        to_target="仓库",
                        quantity=a.shortage_quantity,
                        suggested_timing="7日内",
                        reason=f"缺料 {a.shortage_quantity:.1f}，建议发起采购。",
                    )
                )
            elif a.overstock_quantity > 0:
                actions.append(
                    CoordinationAction(
                        action_type="reduce",
                        material_id=a.material_id,
                        from_source="仓库",
                        to_target="其他产线/退货",
                        quantity=a.overstock_quantity,
                        suggested_timing="本月内",
                        reason=f"积压 {a.overstock_quantity:.1f}，建议减少采购或调配。",
                    )
                )

        for po in po_risks:
            if po.risk_level == "high":
                actions.append(
                    CoordinationAction(
                        action_type="expedite",
                        material_id=po.material_id,
                        from_source=po.supplier_id,
                        to_target="仓库",
                        quantity=0,
                        suggested_timing="立即",
                        reason=f"采购单 {po.po_id} 严重延期，需协调催货。",
                    )
                )

        for rec in purchase_recs[:3]:
            actions.append(
                CoordinationAction(
                    action_type="purchase",
                    material_id=rec.material_id,
                    from_source=rec.recommended_supplier_id,
                    to_target="仓库",
                    quantity=rec.recommended_quantity,
                    suggested_timing=f"{rec.lead_time_days}天内",
                    reason=rec.reason,
                )
            )

        return actions
