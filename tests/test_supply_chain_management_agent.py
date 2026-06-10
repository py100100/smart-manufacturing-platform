from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.agents.supply_chain_management_agent import (
    REQUIRED_NODES,
    SupplyChainManagementAgent,
)
from app.schemas.supply_chain_management import (
    BOMEntry,
    InventoryItem,
    ProductionPlanItem,
    PurchaseOrderItem,
    SupplierInfo,
    SupplyChainManagementRequest,
)
from app.services.supply_chain_management_service import SupplyChainManagementService


# ══════════════════════════════════════════════════════════════════
# 工厂函数
# ══════════════════════════════════════════════════════════════════


def make_plan(plan_id="PLAN-001", product_id="P-1001", quantity=500, priority="high",
              start_date=None, due_date=None) -> ProductionPlanItem:
    return ProductionPlanItem(
        plan_id=plan_id, product_id=product_id, quantity=quantity,
        start_date=start_date or _PLAN_START.isoformat(),
        due_date=due_date or _PLAN_END.isoformat(),
        priority=priority,
    )


def make_bom(product_id="P-1001", material_id="MAT-001", qty_per_unit=2.0) -> BOMEntry:
    return BOMEntry(
        product_id=product_id, material_id=material_id,
        material_name=f"Material-{material_id}",
        quantity_per_unit=qty_per_unit, unit="kg",
    )


def make_inv(material_id="MAT-001", available=500.0, reserved=0.0, safety=200.0,
            max_stock=None) -> InventoryItem:
    return InventoryItem(
        material_id=material_id, material_name=f"Material-{material_id}",
        available_quantity=available, reserved=reserved, safety_stock=safety,
        max_stock=max_stock,
        unit="kg", unit_cost=10.0, lead_time_days=7,
    )


def make_po(po_id="PO-001", material_id="MAT-001", supplier_id="SUP-001",
            qty=200.0, edd=None, status="in_transit", received_qty=0.0) -> PurchaseOrderItem:
    if edd is None:
        edd = _ON_TIME_EDD
    return PurchaseOrderItem(
        po_id=po_id, material_id=material_id, supplier_id=supplier_id,
        order_quantity=qty, expected_delivery_date=edd, status=status,
        received_quantity=received_qty,
    )


def make_supplier(supplier_id="SUP-001", material_ids=None, on_time=0.95,
                  quality=0.98, price=10.0, price_score=0.0,
                  risk_level="low", lead_time=5) -> SupplierInfo:
    return SupplierInfo(
        supplier_id=supplier_id, supplier_name=f"Supplier-{supplier_id}",
        material_ids=material_ids or ["MAT-001"],
        on_time_delivery_rate=on_time, quality_pass_rate=quality,
        price_score=price_score, unit_price=price,
        risk_level=risk_level, lead_time_days=lead_time,
    )


def make_request(**overrides) -> SupplyChainManagementRequest:
    kwargs = {
        "production_plan": [make_plan()],
        "bill_of_materials": [make_bom()],
        "inventory": [make_inv()],
        "purchase_orders": [],
        "suppliers": [],
    }
    kwargs.update(overrides)
    return SupplyChainManagementRequest(**kwargs)


# 动态日期，消除测试对固定日期的脆弱依赖。
# _PLAN_START 始终在 5 天后，_ON_TIME_EDD 与计划开始日相同 →
# PO 不会因 "today 超过 start_date" 被误判为延期，也不会因
# "edd > start_date" 被排除出 in_transit_on_time。
_TODAY = datetime.now().date()
_PLAN_START = _TODAY + timedelta(days=5)
_PLAN_END = _PLAN_START + timedelta(days=2)
_ON_TIME_EDD = _PLAN_START.isoformat()
_LATE_EDD = (_PLAN_START + timedelta(days=5)).isoformat()

# ══════════════════════════════════════════════════════════════════
# 场景 1：库存充足 → supply_chain_stable
# ══════════════════════════════════════════════════════════════════


class TestSupplyChainStable:
    def test_stable_supply_chain(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=50)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=500.0, safety=300.0)],  # 500 < 300*2=600 → no overstock
        )
        output = agent.execute(request)

        assert output.decision == "supply_chain_stable"

    def test_with_in_transit_po(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=50)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 100
            inventory=[make_inv(available=50.0, safety=100.0)],
            purchase_orders=[make_po(qty=200.0, edd=_ON_TIME_EDD)],  # 在途 200，到货日 ≤ 最早开工日
        )
        output = agent.execute(request)

        # projected = 50 + 200 = 250, required+safety = 200 → no shortage → stable
        assert output.decision == "supply_chain_stable"

    def test_all_required_nodes(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request()
        output = agent.execute(request)

        node_names = {n.node for n in output.node_feedback}
        for rn in REQUIRED_NODES:
            assert rn in node_names, f"Missing: {rn}"

    def test_output_structure(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert isinstance(output.evidence, list)
        assert isinstance(output.next_actions, list)
        assert len(output.material_demands) >= 1


# ══════════════════════════════════════════════════════════════════
# 场景 2：普通缺料 → shortage_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestShortageRisk:
    def test_shortage_detected(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=300.0, safety=200.0)],  # have 300
            suppliers=[make_supplier(on_time=0.95, quality=0.98, price=10.0)],
        )
        output = agent.execute(request)

        # shortage = max(0, 1000+200-300) = 900 > 200 → critical_shortage
        assert output.decision == "critical_shortage"

    def test_partial_shortage_with_po(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=300.0, safety=200.0)],
            purchase_orders=[make_po(qty=200.0, edd=_ON_TIME_EDD)],  # 按期到货
            suppliers=[make_supplier(on_time=0.95, quality=0.98)],
        )
        output = agent.execute(request)

        # projected = 300 + 200 = 500, shortage = max(0, 1000+200-500) = 700 > 200 → critical
        assert output.decision == "critical_shortage"


# ══════════════════════════════════════════════════════════════════
# 场景 3：严重缺料 → critical_shortage
# ══════════════════════════════════════════════════════════════════


class TestCriticalShortage:
    def test_zero_stock_critical(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=0.0, safety=200.0)],  # zero
        )
        output = agent.execute(request)

        assert output.decision == "critical_shortage"

    def test_critical_next_actions(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=0.0, safety=200.0)],
        )
        output = agent.execute(request)

        assert any("紧急" in a for a in output.next_actions)


# ══════════════════════════════════════════════════════════════════
# 场景 4：生成采购建议 → purchase_recommended
# ══════════════════════════════════════════════════════════════════


class TestPurchaseRecommended:
    def test_purchase_with_supplier(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=300.0, safety=200.0)],  # have 300
            suppliers=[make_supplier(on_time=0.95, quality=0.98, price=10.0)],
        )
        output = agent.execute(request)

        # shortage = max(0, 1000+200-300) = 900 > 200 → critical_shortage
        assert output.decision == "critical_shortage"
        # 采购建议仍应生成
        assert len(output.purchase_recommendations) >= 1
        rec = output.purchase_recommendations[0]
        assert rec.recommended_quantity == 900.0
        assert rec.recommended_supplier_id == "SUP-001"

    def test_multiple_materials_purchase(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[
                make_bom(material_id="MAT-001", qty_per_unit=2.0),
                make_bom(material_id="MAT-002", qty_per_unit=3.0),
            ],
            inventory=[
                make_inv(material_id="MAT-001", available=50.0, safety=50.0),
                make_inv(material_id="MAT-002", available=0.0, safety=100.0),
            ],
            suppliers=[
                make_supplier(material_ids=["MAT-001"]),
                make_supplier(supplier_id="SUP-002", material_ids=["MAT-002"]),
            ],
        )
        output = agent.execute(request)

        assert len(output.purchase_recommendations) >= 2


# ══════════════════════════════════════════════════════════════════
# 场景 5：积压库存 → overstock_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestOverstockRisk:
    def test_overstock_detected(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],  # low demand → need 10
            bill_of_materials=[make_bom(qty_per_unit=1.0)],  # need 10
            inventory=[make_inv(available=1000.0, safety=100.0, max_stock=200.0)],
        )
        output = agent.execute(request)

        # useable=1000 > max_stock=200 → overstock
        assert output.decision == "overstock_risk_detected"

    def test_overstock_next_actions(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=1.0)],
            inventory=[make_inv(available=1000.0, safety=100.0, max_stock=200.0)],
        )
        output = agent.execute(request)

        assert any("积压" in a or "采购" in a for a in output.next_actions)


# ══════════════════════════════════════════════════════════════════
# 场景 6：高风险供应商 → supplier_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestSupplierRisk:
    def test_low_performance_supplier(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=100.0, safety=200.0)],
            suppliers=[make_supplier(on_time=0.3, quality=0.5, price=10.0)],
        )
        output = agent.execute(request)

        # composite=0.3<0.4 → risk_level="high" → supplier_risk_detected 优先
        assert output.decision == "supplier_risk_detected"
        assert any("供应商" in a for a in output.next_actions)

    def test_supplier_suspended_not_recommended(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=100.0, safety=200.0)],
            suppliers=[make_supplier(on_time=0.95, quality=0.98)],
        )
        # supplier has good stats → recommended
        output = agent.execute(request)

        for ev in output.supplier_evaluations:
            assert ev.composite_score >= 0.7
            assert ev.recommendation == "recommended"


# ══════════════════════════════════════════════════════════════════
# 场景 7：采购单延期 → po_delay_risk
# ══════════════════════════════════════════════════════════════════


class TestPODelayRisk:
    def test_delayed_po(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=1.0)],
            inventory=[make_inv(available=100.0, safety=50.0)],
            purchase_orders=[
                make_po(po_id="PO-001", edd="2026-01-01", status="delayed"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "po_delay_risk"
        assert len(output.po_delay_risks) >= 1

    def test_overdue_in_transit_po(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=1.0)],
            inventory=[make_inv(available=100.0, safety=50.0)],
            purchase_orders=[
                make_po(po_id="PO-002", edd="2026-01-01", status="in_transit"),
            ],
        )
        output = agent.execute(request)

        # in_transit with past EDD → detected as overdue
        assert output.decision == "po_delay_risk"

    def test_on_time_po_no_risk(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=1.0)],
            inventory=[make_inv(available=100.0, safety=50.0)],
            purchase_orders=[
                make_po(po_id="PO-003", edd="2030-12-31", status="in_transit"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "supply_chain_stable"


# ══════════════════════════════════════════════════════════════════
# 场景 8：缺少 BOM → data_insufficient
# ══════════════════════════════════════════════════════════════════


class TestDataInsufficient:
    def test_empty_bom(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(bill_of_materials=[])
        output = agent.execute(request)

        assert output.decision == "data_insufficient"

    def test_empty_production_plan(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(production_plan=[], bill_of_materials=[])
        output = agent.execute(request)

        validation = next(n for n in output.node_feedback if n.node == "input_validation")
        assert validation.status == "failed"


# ══════════════════════════════════════════════════════════════════
# 场景 9：delivery_first 选准时率最高
# ══════════════════════════════════════════════════════════════════


class TestDeliveryFirst:
    def test_delivery_first_best_on_time(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=100.0, safety=200.0)],
            suppliers=[
                make_supplier(supplier_id="SUP-A", on_time=0.60, quality=0.99, price=5.0),
                make_supplier(supplier_id="SUP-B", on_time=0.98, quality=0.70, price=15.0),
            ],
            optimization_goal="delivery_first",
        )
        output = agent.execute(request)

        rec = output.purchase_recommendations[0]
        assert rec.recommended_supplier_id == "SUP-B"  # best on_time


# ══════════════════════════════════════════════════════════════════
# 场景 10：balanced 综合评分选供应商
# ══════════════════════════════════════════════════════════════════


class TestBalancedScoring:
    def test_balanced_selects_best_composite(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=100.0, safety=200.0)],
            suppliers=[
                make_supplier(supplier_id="SUP-A", on_time=0.60, quality=0.99, price=5.0),
                make_supplier(supplier_id="SUP-B", on_time=0.98, quality=0.70, price=15.0),
            ],
            optimization_goal="balanced",
        )
        output = agent.execute(request)

        # balanced: A=0.6*0.4+0.99*0.3+1.0*0.3=0.837, B=0.98*0.4+0.7*0.3+0.33*0.3=0.701
        rec = output.purchase_recommendations[0]
        assert rec.recommended_supplier_id == "SUP-A"

    def test_balanced_composite_score_calculation(self) -> None:
        from app.services.supply_chain_management_service import SupplyChainManagementService

        svc = SupplyChainManagementService()
        suppliers = [
            make_supplier(supplier_id="SUP-1", on_time=0.8, quality=0.9, price=10.0),
            make_supplier(supplier_id="SUP-2", on_time=0.9, quality=0.8, price=12.0),
        ]
        evals = svc.score_suppliers("MAT-001", suppliers, "balanced")

        assert len(evals) == 2
        assert evals[0].composite_score > 0


# ══════════════════════════════════════════════════════════════════
# 场景 11：在途采购按期到货计入 projected_available
# ══════════════════════════════════════════════════════════════════


class TestProjectedAvailableWithPO:
    def test_po_contributes_to_projected(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=300.0, safety=200.0)],
            purchase_orders=[make_po(qty=1000.0, edd=_ON_TIME_EDD, status="in_transit")],
        )
        output = agent.execute(request)

        # projected = 300 + 1000 = 1300, shortage = max(0, 1000+200-1300) = 0 → stable
        assert output.decision == "supply_chain_stable"

    def test_received_po_not_double_counted(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=300.0, safety=200.0)],
            purchase_orders=[
                make_po(po_id="PO-001", qty=500.0, status="received", received_qty=500.0),
            ],
        )
        output = agent.execute(request)

        # received PO 不应计入在途 → projected = 300
        assess = output.inventory_assessments[0]
        assert assess.in_transit_on_time == 0.0


# ══════════════════════════════════════════════════════════════════
# 周转分析
# ══════════════════════════════════════════════════════════════════


class TestTurnoverAnalysis:
    def test_turnover_results(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 200
            inventory=[make_inv(available=200.0, safety=100.0)],
        )
        output = agent.execute(request)

        assert len(output.turnover_analyses) >= 1
        ta = output.turnover_analyses[0]
        assert ta.turnover_rate > 0

    def test_zero_inventory_turnover(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=0.0, safety=100.0)],
        )
        output = agent.execute(request)

        ta = output.turnover_analyses[0]
        assert "无有效周转" in ta.assessment or ta.turnover_rate == 0


# ══════════════════════════════════════════════════════════════════
# 输入校验
# ══════════════════════════════════════════════════════════════════


class TestInputValidation:
    def test_empty_inventory_rejected(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(inventory=[])
        output = agent.execute(request)

        vn = next(n for n in output.node_feedback if n.node == "input_validation")
        assert vn.status == "failed"

    def test_valid_input_passes(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request()
        output = agent.execute(request)

        vn = next(n for n in output.node_feedback if n.node == "input_validation")
        assert vn.status == "success"


# ══════════════════════════════════════════════════════════════════
# 综合场景
# ══════════════════════════════════════════════════════════════════


class TestComprehensiveScenarios:
    def test_full_pipeline(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[
                make_plan("PLAN-001", "P-1001", 500, "high"),
                make_plan("PLAN-002", "P-1002", 300, "medium"),
            ],
            bill_of_materials=[
                make_bom("P-1001", "MAT-001", 2.0),
                make_bom("P-1001", "MAT-002", 1.5),
                make_bom("P-1002", "MAT-002", 1.0),
                make_bom("P-1002", "MAT-003", 3.0),
            ],
            inventory=[
                make_inv("MAT-001", available=800.0, safety=500.0),
                make_inv("MAT-002", available=400.0, safety=600.0),
                make_inv("MAT-003", available=0.0, safety=300.0),
            ],
            purchase_orders=[
                make_po("PO-001", "MAT-002", "SUP-001", 300.0, _ON_TIME_EDD),
                make_po("PO-002", "MAT-003", "SUP-002", 500.0, "2026-01-01", status="delayed"),
            ],
            suppliers=[
                make_supplier("SUP-001", ["MAT-002"], on_time=0.95, quality=0.98, price=10.0),
                make_supplier("SUP-002", ["MAT-003"], on_time=0.75, quality=0.85, price=12.0),
            ],
        )
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert output.evidence
        assert output.next_actions
        assert len(output.node_feedback) >= 9
        assert len(output.material_demands) >= 2
        assert len(output.inventory_assessments) >= 2

    def test_plan_returns_result(self) -> None:
        agent = SupplyChainManagementAgent()
        result = agent.plan("需要供应链分析", {})
        assert result.summary
        assert result.decision

    def test_build_node_feedback(self) -> None:
        agent = SupplyChainManagementAgent()
        result = agent.plan("供应链", {})
        nodes = agent.build_node_feedback("供应链", result)
        assert len(nodes) == 3


# ══════════════════════════════════════════════════════════════════
# 验收补充：任务书原始样例解析
# ══════════════════════════════════════════════════════════════════


TASK_BOOK_SAMPLE: dict = {
    "production_plan": [
        {
            "plan_id": "PLAN-001",
            "product_id": "P-1001",
            "quantity": 1000,
            "start_date": "2026-06-10",
            "due_date": "2026-06-20",
            "priority": "high",
        }
    ],
    "bill_of_materials": [
        {
            "product_id": "P-1001",
            "material_id": "MAT-001",
            "material_name": "钢材",
            "quantity_per_unit": 2.0,
            "unit": "kg",
        },
    ],
    "inventory": [
        {
            "material_id": "MAT-001",
            "material_name": "钢材",
            "available_quantity": 1200.0,
            "reserved_quantity": 100.0,
            "safety_stock": 300.0,
            "max_stock": 2000.0,
            "unit": "kg",
            "unit_cost": 10.0,
            "lead_time_days": 7,
        },
    ],
    "purchase_orders": [
        {
            "po_id": "PO-001",
            "material_id": "MAT-001",
            "supplier_id": "SUP-001",
            "ordered_quantity": 800.0,
            "expected_arrival_date": "2026-06-09",
            "status": "in_transit",
            "received_quantity": 0.0,
        }
    ],
    "suppliers": [
        {
            "supplier_id": "SUP-001",
            "supplier_name": "优质钢材供应商",
            "material_ids": ["MAT-001"],
            "on_time_delivery_rate": 0.95,
            "quality_score": 0.88,
            "price_score": 0.75,
            "risk_level": "low",
            "lead_time_days": 5,
            "status": "active",
            "cooperation_years": 3.0,
        },
    ],
    "optimization_goal": "delivery_first",
}


class TestTaskBookSampleParsing:
    """验证任务书原始样例可直接解析。"""

    def test_task_book_sample_parses(self) -> None:
        """SupplyChainManagementRequest(**任务书样例) 不应抛 ValidationError。"""
        request = SupplyChainManagementRequest(**TASK_BOOK_SAMPLE)
        assert request is not None
        assert len(request.production_plan) == 1
        assert len(request.bill_of_materials) == 1
        assert len(request.inventory) == 1
        assert len(request.purchase_orders) == 1
        assert len(request.suppliers) == 1

    def test_flat_bom_expands_to_nested_materials(self) -> None:
        """扁平 BOM 格式自动展开为嵌套 materials 结构。"""
        request = SupplyChainManagementRequest(**TASK_BOOK_SAMPLE)
        bom_entry = request.bill_of_materials[0]
        assert len(bom_entry.materials) == 1
        mat = bom_entry.materials[0]
        assert mat.material_id == "MAT-001"
        assert mat.required_quantity_per_unit == 2.0

    def test_task_book_sample_full_pipeline(self) -> None:
        """任务书样例可完整执行并产出结构化输出。"""
        agent = SupplyChainManagementAgent()
        request = SupplyChainManagementRequest(**TASK_BOOK_SAMPLE)
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert len(output.material_demands) == 1
        assert len(output.inventory_assessments) == 1
        assert len(output.node_feedback) >= 9
        # coordination_action_generation 节点必须存在
        coord_nodes = [n for n in output.node_feedback if n.node == "coordination_action_generation"]
        assert len(coord_nodes) == 1

    def test_task_book_purchase_order_field_names(self) -> None:
        """验证任务书原始字段名 ordered_quantity / expected_arrival_date 可解析。"""
        po_raw = {
            "po_id": "PO-TB-001",
            "material_id": "MAT-TB",
            "supplier_id": "SUP-TB",
            "ordered_quantity": 500.0,
            "expected_arrival_date": "2026-07-01",
            "status": "in_transit",
        }
        po = PurchaseOrderItem(**po_raw)
        assert po.order_quantity == 500.0
        assert po.expected_delivery_date == "2026-07-01"
        assert po.po_id == "PO-TB-001"

    def test_task_book_sample_exact_values(self) -> None:
        """验证任务书样例产出的精确计算值。

        任务书公式：
          useable = available - reserved = 1200 - 100 = 1100
          projected = useable + on_time_po = 1100 + 800 = 1900
          shortage = max(0, required + safety_stock - projected)
                   = max(0, 2000 + 300 - 1900) = 400
        """
        request = SupplyChainManagementRequest(**TASK_BOOK_SAMPLE)

        # reserved_quantity alias 生效
        inv = request.inventory[0]
        assert inv.reserved == 100.0

        agent = SupplyChainManagementAgent()
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        assert assess.available_quantity == 1200.0
        assert assess.reserved == 100.0
        assert assess.useable_quantity == 1100.0
        assert assess.in_transit_on_time == 800.0
        assert assess.projected_available == 1900.0
        assert assess.required_quantity == 2000.0
        assert assess.safety_stock == 300.0
        assert assess.shortage_quantity == 400.0

        # shortage = 400, required = 2000, 400/2000 = 0.2 → shortage (not critical)
        assert assess.status == "shortage"
        # decision 不能是 supply_chain_stable
        assert output.decision != "supply_chain_stable"

    def test_task_book_sample_reserved_quantity_alias(self) -> None:
        """reserved_quantity 字段名映射到 reserved。"""
        inv_raw = {
            "material_id": "MAT-RSV",
            "available_quantity": 1000.0,
            "reserved_quantity": 250.0,
            "safety_stock": 100.0,
        }
        inv = InventoryItem(**inv_raw)
        assert inv.reserved == 250.0
        assert inv.available_quantity == 1000.0


# ══════════════════════════════════════════════════════════════════
# 验收补充：在途按期计入 / 延期不计入
# ══════════════════════════════════════════════════════════════════


class TestInTransitOnTimeCounting:
    """在途采购单：按期到货计入 projected_available，延期不计入。"""

    def test_on_time_po_contributes_to_projected(self) -> None:
        """按期在途 PO（到货日 ≤ 最早开工日）应计入 projected_available。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=5.0)],  # need 500
            inventory=[make_inv(available=200.0, safety=100.0)],
            purchase_orders=[
                make_po(po_id="PO-ON-TIME", qty=300.0,
                        edd=_ON_TIME_EDD, status="in_transit"),  # ≤ plan_start
            ],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # useable = 200 - 0 = 200, in_transit_on_time = 300
        assert assess.in_transit_on_time == 300.0
        # projected = 200 + 300 = 500
        assert assess.projected_available == 500.0
        # shortage = max(0, 500+100-500) = 100
        assert assess.shortage_quantity == 100.0

    def test_delayed_po_not_contributed_to_projected(self) -> None:
        """到货日晚于最早开工日的 PO 不计入 in_transit_on_time。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=5.0)],  # need 500
            inventory=[make_inv(available=200.0, safety=100.0)],
            purchase_orders=[
                make_po(po_id="PO-LATE", qty=300.0,
                        edd=_LATE_EDD, status="in_transit"),  # 晚于最早开工日
            ],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # PO 到货日 > 最早开工日 → 不计入在途
        assert assess.in_transit_on_time == 0.0
        # projected = 200 + 0 = 200, shortage = max(0, 500+100-200) = 400
        assert assess.projected_available == 200.0
        assert assess.shortage_quantity == 400.0

    def test_delayed_status_po_not_contributed(self) -> None:
        """status=delayed 的 PO 明确不计入 projected。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=5.0)],
            inventory=[make_inv(available=200.0, safety=100.0)],
            purchase_orders=[
                make_po(po_id="PO-DELAYED", qty=500.0,
                        edd="2030-06-15", status="delayed"),  # 未来日期但状态为延期
            ],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # status != "in_transit" → 不计入 in_transit_on_time
        assert assess.in_transit_on_time == 0.0

    def test_received_status_po_not_contributed(self) -> None:
        """status=received 的 PO 不计入（已入库反映在库存中）。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=5.0)],
            inventory=[make_inv(available=200.0, safety=100.0)],
            purchase_orders=[
                make_po(po_id="PO-RECEIVED", qty=500.0,
                        edd="2030-06-15", status="received", received_qty=500.0),
            ],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        assert assess.in_transit_on_time == 0.0


# ══════════════════════════════════════════════════════════════════
# 验收补充：reserved 扣减
# ══════════════════════════════════════════════════════════════════


class TestReservedDeduction:
    """reserved 应从 available_quantity 中扣减得到 useable_quantity。"""

    def test_reserved_deducted_from_useable(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 200
            inventory=[make_inv(available=500.0, reserved=200.0, safety=100.0)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # useable = max(0, 500 - 200) = 300
        assert assess.useable_quantity == 300.0
        assert assess.available_quantity == 500.0
        assert assess.reserved == 200.0

    def test_reserved_exceeds_available_clamped_to_zero(self) -> None:
        """reserved > available 时 useable 钳位为 0。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=100.0, reserved=300.0, safety=50.0)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # useable = max(0, 100 - 300) = 0
        assert assess.useable_quantity == 0.0

    def test_zero_reserved_no_deduction(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=500.0, reserved=0.0, safety=100.0)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        assert assess.useable_quantity == 500.0


# ══════════════════════════════════════════════════════════════════
# 验收补充：max_stock 积压
# ══════════════════════════════════════════════════════════════════


class TestMaxStockBacklog:
    """max_stock 超限时触发积压判定。"""

    def test_overstock_when_useable_exceeds_max_stock(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],  # need 20
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=1000.0, safety=100.0, max_stock=500.0)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # useable=1000 > max_stock=500, shortage=0 → overstock
        assert assess.overstock_quantity == 500.0  # 1000 - 500
        assert assess.status == "overstock"

    def test_no_overstock_when_useable_within_max_stock(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=300.0, safety=100.0, max_stock=500.0)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # useable=300 <= max_stock=500 → no overstock
        assert assess.overstock_quantity == 0.0

    def test_no_overstock_when_max_stock_is_none(self) -> None:
        """max_stock=None 时不判定积压（max_stock 未配置）。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=1000.0, safety=100.0, max_stock=None)],
        )
        output = agent.execute(request)

        assess = output.inventory_assessments[0]
        # max_stock=None → 不判定积压
        assert assess.overstock_quantity == 0.0

    def test_overstock_not_triggered_when_shortage_exists(self) -> None:
        """缺料时即使超过 max_stock 也不标记为积压（优先处理缺料）。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],  # need 1000
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=2000.0, safety=100.0, max_stock=500.0)],
        )
        output = agent.execute(request)

        # useable=2000 > max_stock=500, but required=1000 → shortage
        # projected=2000, required=1000 → ratio=2.0 → normal
        # But then overstock check: max_stk is not None, shortage_qty <= 0 (0),
        # useable(2000) > max_stk(500) → overstock
        assess = output.inventory_assessments[0]
        # required=1000, projected=2000, no shortage
        assert assess.shortage_quantity == 0.0
        # But overstock should be detected
        assert assess.overstock_quantity > 0


# ══════════════════════════════════════════════════════════════════
# 验收补充：标准节点完整性
# ══════════════════════════════════════════════════════════════════


class TestStandardNodeCompleteness:
    """验证所有标准节点均被覆盖，包括 coordination_action_generation。"""

    def test_all_ten_standard_nodes_present(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=300.0, safety=200.0)],
            suppliers=[make_supplier(on_time=0.95, quality=0.98)],
        )
        output = agent.execute(request)

        node_names = {n.node for n in output.node_feedback}
        for rn in REQUIRED_NODES:
            assert rn in node_names, f"标准节点缺失: {rn}"

    def test_coordination_action_generation_emits_actions(self) -> None:
        """缺料场景应触发协同行动生成。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=100.0, safety=200.0)],  # have 100
            suppliers=[make_supplier(on_time=0.95, quality=0.98, price=10.0)],
        )
        output = agent.execute(request)

        assert len(output.coordination_actions) >= 1
        # 协同行动应包含缺料对应的采购或催货动作
        action_types = {a.action_type for a in output.coordination_actions}
        assert "purchase" in action_types or "expedite" in action_types

    def test_coordination_action_generation_for_overstock(self) -> None:
        """积压场景应触发 reduce 类型协同行动。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=10)],
            bill_of_materials=[make_bom(qty_per_unit=1.0)],
            inventory=[make_inv(available=1000.0, safety=100.0, max_stock=200.0)],
        )
        output = agent.execute(request)

        # 积压场景应有 reduce 类型的协同行动
        action_types = {a.action_type for a in output.coordination_actions}
        assert "reduce" in action_types

    def test_coordination_action_for_po_delay(self) -> None:
        """PO 延期场景应触发 expedite 类型协同行动。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=100)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=500.0, safety=100.0)],
            purchase_orders=[
                make_po(po_id="PO-DELAY", qty=200.0,
                        edd="2020-01-01", status="delayed"),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "po_delay_risk"
        # PO 高风险延期应有 expedite 行动
        action_types = {a.action_type for a in output.coordination_actions}
        assert "expedite" in action_types


# ══════════════════════════════════════════════════════════════════
# 验收补充：供应商字段兼容 & 评分公式 & 采购优先级
# ══════════════════════════════════════════════════════════════════


class TestSupplierTaskBookFields:
    """任务书供应商字段 quality_score / price_score / risk_level 不丢弃。"""

    def test_quality_score_alias_not_discarded(self) -> None:
        s = SupplierInfo(
            supplier_id="SUP-Q",
            quality_score=0.88,
            price_score=0.75,
            risk_level="low",
        )
        assert s.quality_pass_rate == 0.88
        assert s.price_score == 0.75
        assert s.risk_level == "low"

    def test_price_score_not_discarded(self) -> None:
        s = SupplierInfo(
            supplier_id="SUP-P",
            price_score=0.65,
        )
        assert s.price_score == 0.65

    def test_risk_level_not_discarded(self) -> None:
        s = SupplierInfo(
            supplier_id="SUP-R",
            risk_level="high",
        )
        assert s.risk_level == "high"

    def test_task_book_sample_supplier_fields_preserved(self) -> None:
        """TASK_BOOK_SAMPLE 中 quality_score / price_score / risk_level 不丢弃。"""
        request = SupplyChainManagementRequest(**TASK_BOOK_SAMPLE)
        sup = request.suppliers[0]
        assert sup.quality_pass_rate == 0.88
        assert sup.price_score == 0.75
        assert sup.risk_level == "low"


class TestSupplierRiskScoring:
    """high risk 供应商评分应明显低于 low risk。"""

    def test_high_risk_scores_lower_than_low_risk(self) -> None:
        """相同条件下 high risk 供应商评分低于 low risk。"""
        svc = SupplyChainManagementService()
        suppliers = [
            make_supplier("SUP-LOW", on_time=0.9, quality=0.9,
                          price_score=0.8, risk_level="low"),
            make_supplier("SUP-HIGH", on_time=0.9, quality=0.9,
                          price_score=0.8, risk_level="high"),
        ]
        evals = svc.score_suppliers("MAT-001", suppliers, "balanced")

        low_eval = next(e for e in evals if e.supplier_id == "SUP-LOW")
        high_eval = next(e for e in evals if e.supplier_id == "SUP-HIGH")
        # low: 0.9*0.4+0.9*0.3+0.8*0.2+1.0*0.1 = 0.89
        # high: 0.9*0.4+0.9*0.3+0.8*0.2+0.2*0.1 = 0.81
        assert high_eval.composite_score < low_eval.composite_score

    def test_risk_adjustment_values(self) -> None:
        """验证 risk_adjustment: low=1.0, medium=0.6, high=0.2。"""
        from app.services.supply_chain_management_service import RISK_ADJUSTMENT
        assert RISK_ADJUSTMENT["low"] == 1.0
        assert RISK_ADJUSTMENT["medium"] == 0.6
        assert RISK_ADJUSTMENT["high"] == 0.2


class TestPurchaseUrgencyMapping:
    """采购建议 urgency：critical_shortage → urgent，shortage → high。"""

    def test_critical_shortage_urgency_is_urgent(self) -> None:
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=0.0, safety=200.0)],  # critical
            suppliers=[make_supplier(on_time=0.95, quality=0.98, price=10.0)],
        )
        output = agent.execute(request)

        assert output.decision == "critical_shortage"
        rec = output.purchase_recommendations[0]
        assert rec.urgency == "urgent"

    def test_shortage_urgency_is_high(self) -> None:
        """普通缺料 urgency 为 high。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=900.0, safety=50.0)],  # shortage but not critical
            suppliers=[make_supplier(on_time=0.95, quality=0.98, price=10.0)],
        )
        output = agent.execute(request)

        # shortage = max(0, 1000+50-900) = 150, 150/1000 = 0.15 ≤ 0.2 → "shortage"
        rec = output.purchase_recommendations[0]
        assert rec.urgency == "high"


# ══════════════════════════════════════════════════════════════════
# 验收补充：risk_level 保留 + constraints + supplier_risk_detected
# ══════════════════════════════════════════════════════════════════


class TestRiskLevelPreserved:
    """输入 risk_level="high" 必须保留到评估结果，不被高分覆盖。"""

    def test_high_risk_preserved_in_evaluation(self) -> None:
        """即使评分高，risk_level=high 的供应商评估结果仍是 high。"""
        svc = SupplyChainManagementService()
        suppliers = [
            make_supplier("SUP-HR", on_time=0.95, quality=0.95,
                          price_score=0.95, risk_level="high"),
        ]
        evals = svc.score_suppliers("MAT-001", suppliers, "balanced")
        assert len(evals) == 1
        assert evals[0].risk_level == "high"

    def test_high_risk_supplier_triggers_supplier_risk_detected(self) -> None:
        """有缺料 + 推荐供应商 risk_level=high → decision 为 supplier_risk_detected。"""
        agent = SupplyChainManagementAgent()
        request = make_request(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],  # need 1000
            inventory=[make_inv(available=300.0, safety=200.0)],  # shortage
            suppliers=[
                make_supplier("SUP-HR", on_time=0.95, quality=0.95,
                              price_score=0.95, risk_level="high"),
            ],
        )
        output = agent.execute(request)

        # 高风险供应商 + 缺料 → supplier_risk_detected
        assert output.decision == "supplier_risk_detected"
        # 评估结果中 risk_level 仍是 high
        hr_eval = next(e for e in output.supplier_evaluations if e.supplier_id == "SUP-HR")
        assert hr_eval.risk_level == "high"


class TestConstraintsOptimizeFor:
    """任务书 constraints.optimize_for 映射到 optimization_goal。"""

    def test_constraints_optimize_for_balanced(self) -> None:
        """constraints.optimize_for="balanced" 应驱动 balanced 评分公式。"""
        agent = SupplyChainManagementAgent()
        # 模拟任务书格式：传入 constraints 而非 optimization_goal
        request = SupplyChainManagementRequest(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=300.0, safety=200.0)],
            suppliers=[
                make_supplier("SUP-A", on_time=0.60, quality=0.99,
                              price_score=0.9, risk_level="low"),
                make_supplier("SUP-B", on_time=0.98, quality=0.70,
                              price_score=0.5, risk_level="low"),
            ],
            constraints={"optimize_for": "balanced"},
        )
        output = agent.execute(request)

        # balanced 公式：SUP-A > SUP-B（综合评分 SUP-A 更高）
        rec = output.purchase_recommendations[0]
        assert rec.recommended_supplier_id == "SUP-A"

    def test_constraints_without_optimization_goal_falls_back(self) -> None:
        """无 constraints 时 optimization_goal 默认 delivery_first。"""
        request = SupplyChainManagementRequest(
            production_plan=[make_plan(quantity=500)],
            bill_of_materials=[make_bom(qty_per_unit=2.0)],
            inventory=[make_inv(available=300.0, safety=200.0)],
            suppliers=[
                make_supplier("SUP-A", on_time=0.60, quality=0.99,
                              price_score=0.9),
                make_supplier("SUP-B", on_time=0.98, quality=0.70,
                              price_score=0.5),
            ],
        )
        # 默认 delivery_first → 最高准时率 SUP-B
        assert request.optimization_goal == "delivery_first"
        agent = SupplyChainManagementAgent()
        output = agent.execute(request)
        rec = output.purchase_recommendations[0]
        assert rec.recommended_supplier_id == "SUP-B"
