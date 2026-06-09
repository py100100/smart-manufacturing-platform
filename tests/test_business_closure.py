from __future__ import annotations

import pytest

from app.schemas.agent import AgentTaskRequest, NodeFeedback, OrchestrationResponse
from app.schemas.business_closure import (
    ActionItem,
    Alert,
    BusinessClosure,
    Report,
    WorkOrder,
)
from app.services.business_closure_service import BusinessClosureService


# ══════════════════════════════════════════════════════════════════
# 工厂
# ══════════════════════════════════════════════════════════════════


def _orch_response(
    mode="single",
    agent_name="quality_inspection",
    display_name="质量检测",
    decision="quality_risk_detected",
    summary="检测到质量缺陷率超标",
    evidence=None,
    next_actions=None,
    chain=None,
) -> OrchestrationResponse:
    from app.schemas.agent import AgentStep

    if chain is None:
        chain = [
            AgentStep(
                agent_name=agent_name,
                display_name=display_name,
                summary=summary,
                decision=decision,
                evidence=evidence or ["缺陷率 8%，超过阈值 5%"],
                next_actions=next_actions or ["复检批次 B001", "调整工艺参数"],
                node_feedback=[
                    NodeFeedback(
                        node_id=f"{agent_name}-intent",
                        node_name="意图识别",
                        status="completed",
                        detail="质量分析",
                    ),
                    NodeFeedback(
                        node_id=f"{agent_name}-analysis",
                        node_name="规则分析",
                        status="completed",
                        detail=summary,
                    ),
                    NodeFeedback(
                        node_id=f"{agent_name}-decision",
                        node_name="决策输出",
                        status="completed",
                        detail=decision,
                    ),
                ],
            )
        ]

    return OrchestrationResponse(
        trace_id="test-trace",
        request_text="测试请求",
        execution_mode=mode,
        detected_scenes=[agent_name] if mode == "single" else [s.agent_name for s in chain],
        agent_name=agent_name if mode == "single" else "+".join(s.agent_name for s in chain),
        summary=summary,
        decision=chain[0].decision if chain else decision,
        evidence=chain[0].evidence if chain else (evidence or []),
        next_actions=chain[0].next_actions if chain else (next_actions or []),
        agent_chain=chain,
        node_feedback=chain[0].node_feedback if chain else [],
    )


# ══════════════════════════════════════════════════════════════════
# 预警提取
# ══════════════════════════════════════════════════════════════════


class TestAlertExtraction:
    def test_quality_risk_generates_alert(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(decision="quality_risk_detected")
        closure = svc.build_closure(resp)

        assert len(closure.alerts) >= 1
        alert = closure.alerts[0]
        assert alert.severity == "warning"
        assert alert.alert_type == "quality"
        assert "质量" in alert.title

    def test_critical_shortage_generates_critical_alert(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="supply_chain_management",
            display_name="供应链",
            decision="critical_shortage",
        )
        closure = svc.build_closure(resp)

        alert = closure.alerts[0]
        assert alert.severity == "critical"
        assert alert.alert_type == "supply"

    def test_safety_risk_generates_critical_alert(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="predictive_maintenance",
            display_name="预测维护",
            decision="safety_risk_detected",
        )
        closure = svc.build_closure(resp)

        alert = closure.alerts[0]
        assert alert.severity == "critical"
        assert alert.alert_type == "safety"

    def test_parameter_out_of_range_generates_warning(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="process_parameter_optimization",
            display_name="工艺优化",
            decision="parameter_out_of_range",
        )
        closure = svc.build_closure(resp)

        alert = closure.alerts[0]
        assert alert.severity == "warning"
        assert alert.alert_type == "process"

    def test_stable_decision_no_alert(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(decision="parameters_optimal")
        closure = svc.build_closure(resp)

        assert len(closure.alerts) == 0


# ══════════════════════════════════════════════════════════════════
# 工单提取
# ══════════════════════════════════════════════════════════════════


class TestWorkOrderExtraction:
    def test_maintenance_risk_generates_work_order(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="predictive_maintenance",
            display_name="预测维护",
            decision="safety_risk_detected",
        )
        closure = svc.build_closure(resp)

        orders = [o for o in closure.work_orders if o.order_type == "maintenance"]
        assert len(orders) >= 1
        assert orders[0].priority == "urgent"

    def test_supply_shortage_generates_purchase_order(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="supply_chain_management",
            display_name="供应链",
            decision="critical_shortage",
        )
        closure = svc.build_closure(resp)

        orders = [o for o in closure.work_orders if o.order_type == "purchase"]
        assert len(orders) >= 1
        assert orders[0].priority == "urgent"

    def test_process_optimization_recommended_generates_order(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="process_parameter_optimization",
            display_name="工艺优化",
            decision="optimization_recommended",
        )
        closure = svc.build_closure(resp)

        orders = [o for o in closure.work_orders if o.order_type == "optimization"]
        assert len(orders) >= 1
        assert orders[0].priority == "medium"

    def test_quality_risk_generates_inspection_order(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="quality_inspection",
            display_name="质量检测",
            decision="quality_risk_detected",
        )
        closure = svc.build_closure(resp)

        orders = [o for o in closure.work_orders if o.order_type == "inspection"]
        assert len(orders) >= 1

    def test_parameters_optimal_no_work_order(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            agent_name="production_scheduling",
            display_name="生产调度",
            decision="supply_chain_stable",
            summary="当前运行状态正常",
            evidence=["运行数据平稳"],
            next_actions=["按计划执行"],
        )
        closure = svc.build_closure(resp)

        # 稳定决策 + 中性摘要 → 无工单触发
        assert len(closure.work_orders) == 0


# ══════════════════════════════════════════════════════════════════
# 报告提取
# ══════════════════════════════════════════════════════════════════


class TestReportExtraction:
    def test_report_generated_per_agent(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response()
        closure = svc.build_closure(resp)

        assert len(closure.reports) >= 1
        rpt = closure.reports[0]
        assert rpt.title
        assert rpt.summary
        assert len(rpt.findings) >= 1
        assert len(rpt.recommendations) >= 1

    def test_collaborative_generates_composite_report(self) -> None:
        from app.schemas.agent import AgentStep

        chain = [
            AgentStep(
                agent_name="quality_inspection",
                display_name="质量检测",
                summary="质量缺陷",
                decision="quality_risk_detected",
                evidence=["缺陷率超标"],
                next_actions=["复检"],
                node_feedback=[],
            ),
            AgentStep(
                agent_name="predictive_maintenance",
                display_name="预测维护",
                summary="设备需维护",
                decision="safety_risk_detected",
                evidence=["振动超标"],
                next_actions=["停机维护"],
                node_feedback=[],
            ),
        ]
        resp = _orch_response(mode="collaborative", agent_name="quality+predictive", chain=chain)
        closure = BusinessClosureService().build_closure(resp)

        # 2 单 agent 报告 + 1 综合报告
        assert len(closure.reports) == 3
        composite = [r for r in closure.reports if "综合" in r.title]
        assert len(composite) == 1


# ══════════════════════════════════════════════════════════════════
# 行动项提取
# ══════════════════════════════════════════════════════════════════


class TestActionItemExtraction:
    def test_action_items_from_next_actions(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            next_actions=["复检批次 B001", "调整工艺参数", "通知质量主管"],
        )
        closure = svc.build_closure(resp)

        assert len(closure.action_items) == 3
        assert all(isinstance(a, ActionItem) for a in closure.action_items)
        descriptions = {a.description for a in closure.action_items}
        assert "复检批次 B001" in descriptions

    def test_action_items_deduplicated(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(next_actions=["复检批次", "复检批次"])
        closure = svc.build_closure(resp)
        # 去重后只剩 1 条
        assert len(closure.action_items) == 1

    def test_action_item_priority_from_decision(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(decision="critical_shortage", next_actions=["紧急采购"])
        closure = svc.build_closure(resp)

        assert closure.action_items[0].priority == "urgent"

    def test_action_item_initial_status_pending(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(next_actions=["复检"])
        closure = svc.build_closure(resp)

        assert closure.action_items[0].status == "pending"


# ══════════════════════════════════════════════════════════════════
# 业务闭环整体结构
# ══════════════════════════════════════════════════════════════════


class TestBusinessClosureStructure:
    def test_closure_has_all_four_sections(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(decision="quality_risk_detected")
        closure = svc.build_closure(resp)

        assert isinstance(closure, BusinessClosure)
        assert isinstance(closure.alerts, list)
        assert isinstance(closure.work_orders, list)
        assert isinstance(closure.reports, list)
        assert isinstance(closure.action_items, list)

    def test_closure_ids_are_unique(self) -> None:
        svc = BusinessClosureService()
        resp = _orch_response(
            decision="critical_shortage",
            next_actions=["A1", "A2", "A3"],
        )
        closure = svc.build_closure(resp)

        all_ids: list[str] = []
        for a in closure.alerts:
            all_ids.append(a.alert_id)
        for w in closure.work_orders:
            all_ids.append(w.order_id)
        for r in closure.reports:
            all_ids.append(r.report_id)
        for a in closure.action_items:
            all_ids.append(a.item_id)

        assert len(all_ids) == len(set(all_ids)), "存在重复 ID"


# ══════════════════════════════════════════════════════════════════
# 协同模式综合预警
# ══════════════════════════════════════════════════════════════════


class TestCollaborativeAlert:
    def test_multi_agent_risk_generates_composite_alert(self) -> None:
        from app.schemas.agent import AgentStep

        chain = [
            AgentStep(
                agent_name="quality_inspection",
                display_name="质量检测",
                summary="质量缺陷超标",
                decision="quality_risk_detected",
                evidence=["缺陷率 8%"],
                next_actions=["复检"],
                node_feedback=[],
            ),
            AgentStep(
                agent_name="predictive_maintenance",
                display_name="预测维护",
                summary="设备振动异常",
                decision="safety_risk_detected",
                evidence=["振动 12mm/s"],
                next_actions=["停机维护"],
                node_feedback=[],
            ),
        ]
        resp = _orch_response(mode="collaborative", agent_name="quality+predictive", chain=chain)
        closure = BusinessClosureService().build_closure(resp)

        # 至少 3 个预警：2 单 agent + 1 综合
        assert len(closure.alerts) >= 3
        composite = [a for a in closure.alerts if "协同" in a.title]
        assert len(composite) == 1
        assert composite[0].severity == "warning"


# ══════════════════════════════════════════════════════════════════
# API 端点测试
# ══════════════════════════════════════════════════════════════════


class TestAPIClosureEndpoint:
    """统一 /agents/execute 端点 — 返回编排链路 + 业务闭环。"""

    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, text: str, agent_name: str | None = None) -> dict:
        body: dict = {"request_text": text, "require_llm": False}
        if agent_name:
            body["agent_name"] = agent_name
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_unified_execute_returns_closure(self) -> None:
        data = self._post("分析供应链库存缺料风险")
        assert "closure" in data
        c = data["closure"]
        assert "alerts" in c
        assert "work_orders" in c
        assert "reports" in c
        assert "action_items" in c

    def test_single_agent_has_alerts_and_actions(self) -> None:
        data = self._post("设备振动异常需要预测性维护")
        assert data["execution_mode"] == "single"
        c = data["closure"]
        assert len(c["alerts"]) >= 1
        assert len(c["action_items"]) >= 1
        assert len(c["reports"]) >= 1

    def test_collaborative_has_comprehensive_output(self) -> None:
        data = self._post(
            "质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率"
        )
        assert data["execution_mode"] == "collaborative"
        c = data["closure"]
        composite_reports = [r for r in c["reports"] if "综合" in r["title"]]
        assert len(composite_reports) >= 1
        assert len(c["alerts"]) >= 2


# ══════════════════════════════════════════════════════════════════
# 按智能体直接调用端点
# ══════════════════════════════════════════════════════════════════


class TestPerAgentEndpoint:
    """POST /agents/{agent_name}/execute — 直接调用指定智能体。"""

    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, agent_name: str, text: str) -> dict:
        resp = self.client.post(
            f"/api/v1/agents/{agent_name}/execute",
            json={"request_text": text, "require_llm": False},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_per_agent_production_scheduling(self) -> None:
        data = self._post("production_scheduling", "优化排产")
        assert data["execution_mode"] == "single"
        assert data["agent_name"] == "production_scheduling"
        assert "closure" in data

    def test_per_agent_quality_inspection(self) -> None:
        data = self._post("quality_inspection", "分析质量")
        assert data["agent_name"] == "quality_inspection"
        assert "closure" in data

    def test_per_agent_predictive_maintenance(self) -> None:
        data = self._post("predictive_maintenance", "设备维护")
        assert data["agent_name"] == "predictive_maintenance"

    def test_per_agent_supply_chain_management(self) -> None:
        data = self._post("supply_chain_management", "缺料风险")
        assert data["agent_name"] == "supply_chain_management"

    def test_per_agent_process_parameter_optimization(self) -> None:
        data = self._post("process_parameter_optimization", "优化温度")
        assert data["agent_name"] == "process_parameter_optimization"

    def test_per_agent_invalid_name_returns_422(self) -> None:
        resp = self.client.post(
            "/api/v1/agents/unknown_agent/execute",
            json={"request_text": "测试", "require_llm": False},
        )
        assert resp.status_code == 422

    def test_per_agent_ignores_body_agent_name(self) -> None:
        """路径 agent_name 优先 — 请求体中无需传 agent_name。"""
        resp = self.client.post(
            "/api/v1/agents/quality_inspection/execute",
            json={"request_text": "测试质量数据", "require_llm": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "quality_inspection"


# ══════════════════════════════════════════════════════════════════
# GET /agents/ 列表端点
# ══════════════════════════════════════════════════════════════════


class TestListAgentsEndpoint:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_list_agents_returns_five(self) -> None:
        resp = self.client.get("/api/v1/agents/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        names = {a["name"] for a in data}
        assert "supply_chain_management" in names
        assert "process_parameter_optimization" in names

    def test_list_agents_has_metadata(self) -> None:
        resp = self.client.get("/api/v1/agents/")
        data = resp.json()
        for agent in data:
            assert "name" in agent
            assert "display_name" in agent
            assert "input_schema" in agent
            assert "output_schema" in agent


# ══════════════════════════════════════════════════════════════════
# 业务对象字段完整性
# ══════════════════════════════════════════════════════════════════


class TestBusinessObjectFields:
    def test_alert_has_all_required_fields(self) -> None:
        alert = Alert(
            source_agent="test_agent",
            severity="warning",
            alert_type="quality",
            title="测试预警",
            message="测试消息",
        )
        assert alert.alert_id.startswith("ALERT-")
        assert alert.generated_at is not None
        assert alert.acknowledged is False

    def test_work_order_has_all_required_fields(self) -> None:
        wo = WorkOrder(
            source_agent="test_agent",
            order_type="maintenance",
            title="测试工单",
        )
        assert wo.order_id.startswith("WO-")
        assert wo.status == "pending"
        assert wo.created_at is not None

    def test_report_has_all_required_fields(self) -> None:
        rpt = Report(
            source_agents=["agent1"],
            title="测试报告",
            summary="测试摘要",
            findings=["发现1"],
            recommendations=["建议1"],
        )
        assert rpt.report_id.startswith("RPT-")
        assert rpt.generated_at is not None

    def test_action_item_has_all_required_fields(self) -> None:
        item = ActionItem(
            source_agent="test_agent",
            description="执行某操作",
        )
        assert item.item_id.startswith("ACT-")
        assert item.status == "pending"
        assert item.created_at is not None
