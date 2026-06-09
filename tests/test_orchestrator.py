from __future__ import annotations

import pytest

from app.agents.registry import AgentRegistry, get_registry
from app.schemas.agent import AgentTaskRequest, OrchestrationResponse


# ══════════════════════════════════════════════════════════════════
# 统一注册表契约测试
# ══════════════════════════════════════════════════════════════════


class TestAgentRegistryContract:
    AGENT_NAMES = [
        "production_scheduling",
        "quality_inspection",
        "predictive_maintenance",
        "supply_chain_management",
        "process_parameter_optimization",
    ]

    def test_all_five_agents_registered(self) -> None:
        registry = get_registry()
        for name in self.AGENT_NAMES:
            assert registry.get(name) is not None, f"未注册: {name}"

    def test_all_agents_have_metadata(self) -> None:
        registry = get_registry()
        for name in self.AGENT_NAMES:
            meta = registry.meta(name)
            assert meta.display_name
            assert meta.input_schema
            assert meta.output_schema

    def test_all_agents_plan_returns_five_fields(self) -> None:
        registry = get_registry()
        for name in self.AGENT_NAMES:
            agent = registry.get(name)
            result = agent.plan("测试请求", {})
            missing = AgentRegistry.verify_output_contract(result)
            assert missing == [], f"{name}: 缺失字段 {missing}"

    def test_all_agents_execute_returns_five_fields(self) -> None:
        from app.schemas.predictive_maintenance import (
            EquipmentInfo, PredictiveMaintenanceRequest,
        )
        from app.schemas.process_parameter_optimization import (
            ProcessInfo, ProcessParameterOptimizationRequest,
        )
        from app.schemas.production_scheduling import (
            EquipmentInput, OrderInput, ProcessRouteInput, ProcessStepInput,
            SchedulingRequest, WorkOrderInput,
        )
        from app.schemas.quality_inspection import (
            InspectionBatch, QualityInspectionRequest,
        )
        from app.schemas.supply_chain_management import (
            SupplyChainManagementRequest,
        )

        registry = get_registry()
        fixtures = {
            "production_scheduling": SchedulingRequest(
                orders=[OrderInput(order_id="ORD-1", product_id="P-1", quantity=10, due_date="2026-12-31")],
                work_orders=[WorkOrderInput(work_order_id="WO-1", order_id="ORD-1", product_id="P-1", quantity=10)],
                process_routes=[ProcessRouteInput(
                    route_id="R-1", product_id="P-1",
                    steps=[ProcessStepInput(step_id="S1", step_name="CNC", sequence=1, standard_minutes_per_unit=5.0)],
                )],
                equipment=[EquipmentInput(equipment_id="EQ-1", equipment_name="CNC", equipment_type="machining", available_minutes_per_day=480, cost_per_hour=150.0)],
                optimization_goal="delivery_first",
            ),
            "quality_inspection": QualityInspectionRequest(
                inspection_batch=InspectionBatch(batch_id="B-001", product_id="P-001", process_step="cnc", inspection_time="2026-06-10T08:00:00"),
                inspection_items=[], defect_records=[],
            ),
            "predictive_maintenance": PredictiveMaintenanceRequest(
                equipment=EquipmentInfo(equipment_id="EQ-001", equipment_type="CNC"),
                sensor_readings=[], maintenance_history=[],
            ),
            "supply_chain_management": SupplyChainManagementRequest(
                production_plan=[], bill_of_materials=[],
                inventory=[], purchase_orders=[], suppliers=[],
            ),
            "process_parameter_optimization": ProcessParameterOptimizationRequest(
                process=ProcessInfo(process_id="PROC-001"),
                historical_batches=[], parameter_constraints=[],
                current_parameters={}, quality_feedback=[],
            ),
        }
        for name in self.AGENT_NAMES:
            agent = registry.get(name)
            output = agent.execute(fixtures[name])
            missing = AgentRegistry.verify_output_contract(output)
            assert missing == [], f"{name}.execute(): 缺失字段 {missing}"


# ══════════════════════════════════════════════════════════════════
# 场景检测测试
# ══════════════════════════════════════════════════════════════════


class TestSceneDetection:
    def test_single_scene_detected(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        scenes = orch.detect_scenes("请分析最近的质量缺陷和不良率原因")
        assert "quality_inspection" in scenes
        assert len(scenes) >= 1

    def test_multi_scene_detected(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        scenes = orch.detect_scenes("质量缺陷导致设备振动，需要维护并优化工艺参数")
        assert "quality_inspection" in scenes
        assert "predictive_maintenance" in scenes
        assert "process_parameter_optimization" in scenes
        assert len(scenes) >= 3

    def test_supply_chain_and_scheduling_scene(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        scenes = orch.detect_scenes("排产前需要先检查库存和供应链物料是否充足")
        assert "supply_chain_management" in scenes
        assert "production_scheduling" in scenes

    def test_no_match_returns_empty(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        scenes = orch.detect_scenes("今天天气不错")
        assert scenes == []


# ══════════════════════════════════════════════════════════════════
# 路由测试
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorRouting:
    def test_quality_request_routes_to_quality_inspection(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="请分析最近批次的质量缺陷和不良率原因", require_llm=False)
        assert orch.route_agent(req) == "quality_inspection"

    def test_supply_chain_routes_correctly(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="分析供应链库存缺料风险", require_llm=False)
        assert orch.route_agent(req) == "supply_chain_management"

    def test_maintenance_routes_correctly(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="设备振动异常需要预测性维护", require_llm=False)
        assert orch.route_agent(req) == "predictive_maintenance"

    def test_scheduling_routes_correctly(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="请优化排产计划提升产能", require_llm=False)
        assert orch.route_agent(req) == "production_scheduling"

    def test_process_optimization_routes_correctly(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="优化热处理工艺温度和压力参数", require_llm=False)
        assert orch.route_agent(req) == "process_parameter_optimization"

    def test_unknown_defaults_to_production_scheduling(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="帮我随便看看", require_llm=False)
        assert orch.route_agent(req) == "production_scheduling"

    def test_explicit_agent_name_overrides_routing(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="分析质量缺陷", agent_name="supply_chain_management", require_llm=False)
        assert orch.route_agent(req) == "supply_chain_management"


# ══════════════════════════════════════════════════════════════════
# 单智能体集成测试
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorSingleAgent:
    """通过 Orchestrator.execute() 调用单智能体。"""

    @pytest.mark.asyncio
    async def test_execute_production_scheduling(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="请优化排产计划提升产能", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "single"
        assert resp.agent_name == "production_scheduling"
        assert len(resp.node_feedback) >= 3
        assert len(resp.agent_chain) == 1

    @pytest.mark.asyncio
    async def test_execute_quality_inspection(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="请分析最近批次的质量缺陷和不良率原因", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "single"
        assert resp.agent_name == "quality_inspection"
        assert len(resp.node_feedback) >= 3

    @pytest.mark.asyncio
    async def test_execute_predictive_maintenance(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="设备振动异常需要预测性维护", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.agent_name == "predictive_maintenance"
        assert len(resp.node_feedback) >= 3

    @pytest.mark.asyncio
    async def test_execute_supply_chain_management(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="分析供应链库存缺料风险", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.agent_name == "supply_chain_management"
        assert len(resp.node_feedback) >= 3

    @pytest.mark.asyncio
    async def test_execute_process_parameter_optimization(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="优化热处理工艺温度和压力参数", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.agent_name == "process_parameter_optimization"
        assert len(resp.node_feedback) >= 3

    @pytest.mark.asyncio
    async def test_explicit_agent_name_single_mode(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="随便什么内容", agent_name="supply_chain_management", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "single"
        assert resp.agent_name == "supply_chain_management"


# ══════════════════════════════════════════════════════════════════
# 多智能体协同集成测试
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorCollaborative:
    """多智能体协同调用 — 验证检测、链执行、聚合反馈。"""

    @pytest.mark.asyncio
    async def test_quality_and_maintenance_collaborative(self) -> None:
        """质量缺陷 + 设备振动 → 双智能体协同。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，同时设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"
        assert len(resp.agent_chain) == 2
        agent_names = [s.agent_name for s in resp.agent_chain]
        assert "quality_inspection" in agent_names
        assert "predictive_maintenance" in agent_names

    @pytest.mark.asyncio
    async def test_supply_chain_and_scheduling_collaborative(self) -> None:
        """供应链 + 排产 → 先检查物料再排产。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="排产前需要检查供应链库存是否充足，避免缺料影响交期",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"
        agent_names = [s.agent_name for s in resp.agent_chain]
        # 供应链先于排产
        assert agent_names[0] == "supply_chain_management"
        assert agent_names[1] == "production_scheduling"

    @pytest.mark.asyncio
    async def test_quality_and_process_collaborative(self) -> None:
        """质量缺陷 + 工艺优化 → 先分析质量再优化工艺。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量良率低于目标，需要优化工艺温度和压力参数来提升",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"
        agent_names = [s.agent_name for s in resp.agent_chain]
        assert "quality_inspection" in agent_names
        assert "process_parameter_optimization" in agent_names

    @pytest.mark.asyncio
    async def test_three_agent_full_chain(self) -> None:
        """质量 + 设备 + 工艺 → 三智能体全链路。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动传感器报警，需要优化工艺参数来改善良品率",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"
        assert len(resp.agent_chain) == 3

    @pytest.mark.asyncio
    async def test_collaborative_aggregated_node_feedback(self) -> None:
        """多智能体协同的聚合 node_feedback 包含所有 agent 的节点。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        # 聚合节点数 >= 6（2 agent × 3 节点）
        assert len(resp.node_feedback) >= 6
        # 每个 agent_step 也有自己的 node_feedback
        for step in resp.agent_chain:
            assert len(step.node_feedback) >= 3

    @pytest.mark.asyncio
    async def test_collaborative_response_has_complete_chain(self) -> None:
        """协同响应包含完整链路信息。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="排产前需要检查供应链库存是否充足，避免缺料影响交期",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        # 顶层字段
        assert resp.execution_mode == "collaborative"
        assert resp.summary
        assert resp.decision
        assert len(resp.evidence) >= 2
        assert len(resp.next_actions) >= 2
        assert len(resp.agent_chain) >= 2
        assert len(resp.detected_scenes) >= 2
        # agent_chain 中每个 step 都有简介
        for step in resp.agent_chain:
            assert step.agent_name
            assert step.display_name
            assert step.summary
            assert step.decision

    @pytest.mark.asyncio
    async def test_single_scene_still_returns_full_orchestration_response(self) -> None:
        """单场景也返回完整的 OrchestrationResponse 结构。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(request_text="优化排产计划", require_llm=False)
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "single"
        assert resp.trace_id
        assert resp.summary
        assert resp.decision
        assert len(resp.evidence) >= 1
        assert len(resp.next_actions) >= 1
        assert len(resp.node_feedback) >= 3
        assert len(resp.agent_chain) == 1


# ══════════════════════════════════════════════════════════════════
# resolve_chain 单元测试
# ══════════════════════════════════════════════════════════════════


class TestResolveChain:
    def test_two_scenes_resolves_to_predefined_chain(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        chain = orch.resolve_chain(["quality_inspection", "predictive_maintenance"])
        assert chain is not None
        assert len(chain) == 2

    def test_single_scene_returns_none(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        chain = orch.resolve_chain(["quality_inspection"])
        assert chain is None

    def test_unmatched_pair_returns_none(self) -> None:
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        # process + scheduling has no predefined chain
        chain = orch.resolve_chain(["process_parameter_optimization", "production_scheduling"])
        assert chain is None


# ══════════════════════════════════════════════════════════════════
# API 层集成测试：FastAPI TestClient 验证 JSON 契约
# ══════════════════════════════════════════════════════════════════


class TestAPIExecuteEndpoint:
    """通过 FastAPI TestClient 验证 /agents/execute 返回完整 OrchestrationResponse。"""

    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def _post(self, request_text: str, agent_name: str | None = None) -> dict:
        body: dict = {"request_text": request_text, "require_llm": False}
        if agent_name:
            body["agent_name"] = agent_name
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    # ── 单智能体 ──────────────────────────────────────────

    def test_api_single_agent_returns_execution_mode(self) -> None:
        data = self._post("优化排产计划提升产能")
        assert data["execution_mode"] == "single"
        assert data["agent_name"] == "production_scheduling"
        assert len(data["agent_chain"]) == 1
        assert len(data["node_feedback"]) >= 3

    def test_api_single_agent_has_required_top_fields(self) -> None:
        data = self._post("分析供应链库存缺料风险")
        assert "trace_id" in data
        assert "summary" in data
        assert "decision" in data
        assert "evidence" in data
        assert "next_actions" in data
        assert "node_feedback" in data
        assert "agent_chain" in data
        assert "detected_scenes" in data
        assert "execution_mode" in data

    def test_api_explicit_agent_name_single_mode(self) -> None:
        data = self._post("随便什么内容", agent_name="predictive_maintenance")
        assert data["execution_mode"] == "single"
        assert data["agent_name"] == "predictive_maintenance"

    # ── 多智能体协同 ──────────────────────────────────────

    def test_api_collaborative_returns_execution_mode(self) -> None:
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")
        assert data["execution_mode"] == "collaborative"
        assert len(data["detected_scenes"]) >= 2

    def test_api_collaborative_has_agent_chain(self) -> None:
        data = self._post("排产前需要检查供应链库存是否充足，避免缺料影响交期")
        assert data["execution_mode"] == "collaborative"
        chain = data["agent_chain"]
        assert len(chain) == 2
        for step in chain:
            assert "agent_name" in step
            assert "display_name" in step
            assert "summary" in step
            assert "decision" in step
            assert "node_feedback" in step
            assert len(step["node_feedback"]) >= 3

    def test_api_collaborative_aggregated_node_feedback(self) -> None:
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")
        assert data["execution_mode"] == "collaborative"
        # 聚合 node_feedback >= 6 (2 agents × 3 nodes)
        assert len(data["node_feedback"]) >= 6
        # detected_scenes 包含两个域
        assert "quality_inspection" in data["detected_scenes"]
        assert "predictive_maintenance" in data["detected_scenes"]

    def test_api_collaborative_top_level_fields_present(self) -> None:
        data = self._post("质量缺陷率上升，同时需要优化工艺参数来改善良品率")
        assert data["execution_mode"] == "collaborative"
        assert data["summary"]
        assert data["decision"]
        assert len(data["evidence"]) >= 2
        assert len(data["next_actions"]) >= 2
        assert len(data["agent_chain"]) == 2

    def test_api_three_agent_full_chain(self) -> None:
        data = self._post("质量缺陷率上升，设备振动传感器报警，需要优化工艺参数来改善良品率")
        assert data["execution_mode"] == "collaborative"
        assert len(data["agent_chain"]) == 3
        assert len(data["detected_scenes"]) >= 3
