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


# ══════════════════════════════════════════════════════════════════
# 知识解释型问题识别测试
# ══════════════════════════════════════════════════════════════════


class TestKnowledgeQuestionDetection:
    """验证 _matches_knowledge_question 的保守判定逻辑。"""

    @pytest.mark.parametrize("text, expected", [
        # ── 应判定为知识型 ──
        (
            "基于振动、温度等传感器数据预测设备剩余寿命时，如何动态设定报警阈值以减少误报与漏报？请提出一种结合统计过程控制与深度学习的自适应阈值方法。",
            True,
        ),
        ("如何降低CNC设备的误报率？", True),
        ("请设计一个自适应报警阈值的方案", True),
        ("解释一下预测性维护中的剩余寿命预测方法", True),
        ("设计一个方案来减少传感器误报和漏报", True),
        ("结合统计过程控制与深度学习的方法有哪些", True),
        ("怎么做设备的动态阈值报警？", True),
        ("提出一种基于SPC和LSTM的自适应方法", True),
        ("how to design an adaptive threshold method", True),
        ("explain how to reduce false positives in predictive maintenance", True),
        # ── 不应判定为知识型（普通业务问题） ──
        ("最近批次缺陷率上升至8%，请分析根因", False),
        ("设备CNC-001振动传感器报警", False),
        ("请检查供应链库存是否充足", False),
        ("排产计划需要优化", False),
    ])
    def test_knowledge_question_detection(self, text: str, expected: bool) -> None:
        from app.services.orchestrator import _matches_knowledge_question
        assert _matches_knowledge_question(text) == expected, f"text={text!r}"


# ══════════════════════════════════════════════════════════════════
# 业务解释型问题检测 — _is_business_explanation_question
# ══════════════════════════════════════════════════════════════════


class TestBusinessExplanationDetection:
    """验证 _is_business_explanation_question 对五大业务模块的识别。"""

    FIVE_BUSINESS_QUESTIONS: list[tuple[str, str]] = [
        # (问题, 期望命中的业务领域)
        (
            "订单交期集中但设备产能不足，如何优化排产？",
            "production_scheduling",
        ),
        (
            "如何根据库存、BOM和在途采购判断缺料风险？",
            "supply_chain_management",
        ),
        (
            "如何根据质量反馈优化工艺参数？",
            "process_parameter_optimization",
        ),
        (
            "最近批次缺陷率上升至8%，主要缺陷为尺寸偏差，请分析根因并给出改进建议",
            "quality_inspection",
        ),
        (
            "设备振动传感器读数持续升高，如何判断是否需要维护？",
            "predictive_maintenance",
        ),
    ]

    @pytest.mark.parametrize("text, expected_domain", FIVE_BUSINESS_QUESTIONS)
    def test_business_question_detected(self, text: str, expected_domain: str) -> None:
        """五个典型业务问题都应被 _is_business_explanation_question 命中。"""
        from app.services.business_answer_service import (
            _is_business_explanation_question,
        )
        assert _is_business_explanation_question(text), (
            f"应命中但未命中: {text!r}"
        )

    @pytest.mark.parametrize("text, expected_domain", FIVE_BUSINESS_QUESTIONS)
    def test_business_domain_detected(self, text: str, expected_domain: str) -> None:
        """五个问题都应检测到正确的业务领域。"""
        from app.services.business_answer_service import (
            _detect_business_domains,
        )
        domains = _detect_business_domains(text)
        assert domains.get(expected_domain, False), (
            f"领域 {expected_domain} 应命中但未命中: {text!r}, "
            f"命中领域: {[k for k, v in domains.items() if v]}"
        )

    @pytest.mark.parametrize("text, expected", [
        # ── 应判定为业务解释型 ──
        ("如何优化排产计划？", True),
        ("怎么判断库存是否缺料？", True),
        ("为什么最近缺陷率上升了？", True),
        ("请分析设备故障的根本原因", True),
        ("如何提高良品率？", True),
        ("请分析供应链库存风险", True),
        ("怎样优化工艺参数提升良品率？", True),
        ("怎么降低产线瓶颈？", True),
        # ── 不应判定为业务解释型（无解释型问法或无业务关键词）──
        ("今天天气不错", False),
        ("设备CNC-001振动传感器报警", False),  # 无解释型问法
        ("你好", False),  # 太短
        ("请帮我查一下库存", False),  # 查一下不是解释型问法
    ])
    def test_is_business_explanation_question(
        self, text: str, expected: bool
    ) -> None:
        """验证 _is_business_explanation_question 的判定逻辑。"""
        from app.services.business_answer_service import (
            _is_business_explanation_question,
        )
        assert _is_business_explanation_question(text) == expected, (
            f"text={text!r}, expected={expected}"
        )


class TestBusinessDomainKeywords:
    """验证五大业务领域关键词覆盖。"""

    def test_all_five_domains_have_keywords(self) -> None:
        """五个业务领域各有至少 5 个关键词。"""
        from app.services.business_answer_service import BUSINESS_DOMAIN_KEYWORDS
        expected = [
            "production_scheduling",
            "quality_inspection",
            "predictive_maintenance",
            "supply_chain_management",
            "process_parameter_optimization",
        ]
        for domain in expected:
            assert domain in BUSINESS_DOMAIN_KEYWORDS, f"缺少领域: {domain}"
            assert len(BUSINESS_DOMAIN_KEYWORDS[domain]) >= 5, (
                f"{domain} 关键词不足 5 个: {BUSINESS_DOMAIN_KEYWORDS[domain]}"
            )

    def test_business_domains_distinct_from_knowledge_domains(self) -> None:
        """业务领域函数独立于知识领域函数。"""
        from app.services.business_answer_service import (
            _detect_business_domains,
            _detect_knowledge_domains,
        )
        text = "如何优化排产计划提升产能？"
        biz = _detect_business_domains(text)
        knowledge = _detect_knowledge_domains(text)

        # 业务领域检测到 production_scheduling
        assert biz.get("production_scheduling", False)
        # 知识领域不会把这些关键词当知识型
        assert not any(knowledge.values())

    def test_detect_all_domains_merges_both(self) -> None:
        """_detect_all_domains 合并业务与知识领域。"""
        from app.services.business_answer_service import _detect_all_domains
        text = "如何优化排产并降低设备振动误报？"
        domains = _detect_all_domains(text)

        assert domains.get("production_scheduling", False)
        assert domains.get("predictive_maintenance", False)
        # 同时也有知识领域命中
        assert domains.get("sensor", False) or domains.get("fpfn", False)


class TestBusinessExpertTemplates:
    """验证五大业务模块专家模板的完整性和内容深度。

    每个模板必须：
    - 产出 ≥ 500 字的专家级回答
    - 覆盖任务书要求的全部问题类型
    - 包含方法、公式、步骤、实施建议
    - 不包含空洞流程摘要
    """

    # ── 1. 生产调度优化 ────────────────────────────────────

    def test_production_scheduling_template_exists_and_rich(self) -> None:
        from app.services.business_answer_service import (
            _generate_production_scheduling_answer,
        )
        answer = _generate_production_scheduling_answer()
        assert len(answer) > 500, f"模板过短: {len(answer)} 字"

    @pytest.mark.parametrize("keyword", [
        "EDD", "SPT", "Critical Ratio", "瓶颈优先", "滚动排程",
        "排程目标", "排程方法", "约束条件", "交期冲突",
        "多设备多工序多订单", "工单排序表", "设备分配甘特图",
        "瓶颈设备清单", "延期风险", "持续改进建议",
    ])
    def test_production_scheduling_has_required_sections(self, keyword: str) -> None:
        from app.services.business_answer_service import (
            _generate_production_scheduling_answer,
        )
        answer = _generate_production_scheduling_answer()
        assert keyword in answer, f"缺少关键内容: {keyword}"

    # ── 2. 质量检测与缺陷分析 ──────────────────────────────

    def test_quality_inspection_template_exists_and_rich(self) -> None:
        from app.services.business_answer_service import (
            _generate_quality_inspection_answer,
        )
        answer = _generate_quality_inspection_answer()
        assert len(answer) > 500, f"模板过短: {len(answer)} 字"

    @pytest.mark.parametrize("keyword", [
        "缺陷分类", "检测指标", "8D", "根因分析", "4M1E",
        "人机料法环", "鱼骨图", "尺寸偏差", "表面粗糙度",
        "裂纹", "气孔", "历史缺陷", "改进措施", "预防",
        "Cpk", "DPPM", "FMEA", "Poka-Yoke",
    ])
    def test_quality_inspection_has_required_sections(self, keyword: str) -> None:
        from app.services.business_answer_service import (
            _generate_quality_inspection_answer,
        )
        answer = _generate_quality_inspection_answer()
        assert keyword in answer, f"缺少关键内容: {keyword}"

    # ── 3. 设备预测性维护 ──────────────────────────────────

    def test_predictive_maintenance_template_exists_and_rich(self) -> None:
        from app.services.business_answer_service import (
            _generate_predictive_maintenance_business_answer,
        )
        answer = _generate_predictive_maintenance_business_answer()
        assert len(answer) > 500, f"模板过短: {len(answer)} 字"

    @pytest.mark.parametrize("keyword", [
        "数据采集", "特征提取", "趋势分析", "SPC", "EWMA",
        "CUSUM", "异常检测", "AutoEncoder", "RUL", "LSTM",
        "动态报警阈值", "误报", "漏报", "滞后报警",
        "多传感器联合判定", "维护工单", "EAM", "SHAP",
    ])
    def test_predictive_maintenance_has_required_sections(self, keyword: str) -> None:
        from app.services.business_answer_service import (
            _generate_predictive_maintenance_business_answer,
        )
        answer = _generate_predictive_maintenance_business_answer()
        assert keyword in answer, f"缺少关键内容: {keyword}"

    # ── 4. 供应链协同管理 ──────────────────────────────────

    def test_supply_chain_template_exists_and_rich(self) -> None:
        from app.services.business_answer_service import (
            _generate_supply_chain_management_answer,
        )
        answer = _generate_supply_chain_management_answer()
        assert len(answer) > 500, f"模板过短: {len(answer)} 字"

    @pytest.mark.parametrize("keyword", [
        "BOM", "MRP", "需求预测", "安全库存", "scheduled_receipt",
        "缺料风险", "库存周转", "ABC 分类", "供应商评估",
        "Scorecard", "采购建议", "EOQ", "供应商评分",
        "VMI", "积压", "断供", "S&OP",
    ])
    def test_supply_chain_has_required_sections(self, keyword: str) -> None:
        from app.services.business_answer_service import (
            _generate_supply_chain_management_answer,
        )
        answer = _generate_supply_chain_management_answer()
        assert keyword in answer, f"缺少关键内容: {keyword}"

    # ── 5. 工艺参数优化 ────────────────────────────────────

    def test_process_parameter_template_exists_and_rich(self) -> None:
        from app.services.business_answer_service import (
            _generate_process_parameter_optimization_answer,
        )
        answer = _generate_process_parameter_optimization_answer()
        assert len(answer) > 500, f"模板过短: {len(answer)} 字"

    @pytest.mark.parametrize("keyword", [
        "关键参数", "质量指标", "敏感性分析", "ANOVA", "DOE",
        "响应面", "RSM", "贝叶斯优化", "EI",
        "Pareto Front", "帕累托", "田口方法", "Taguchi",
        "参数组合推荐", "缺陷率", "PDCA", "SPC", "数字孪生",
    ])
    def test_process_parameter_has_required_sections(self, keyword: str) -> None:
        from app.services.business_answer_service import (
            _generate_process_parameter_optimization_answer,
        )
        answer = _generate_process_parameter_optimization_answer()
        assert keyword in answer, f"缺少关键内容: {keyword}"

    # ── 6. 通用检查：所有模板不含空洞摘要 ──────────────────

    @pytest.mark.parametrize("template_fn_name", [
        "_generate_production_scheduling_answer",
        "_generate_quality_inspection_answer",
        "_generate_predictive_maintenance_business_answer",
        "_generate_supply_chain_management_answer",
        "_generate_process_parameter_optimization_answer",
    ])
    def test_all_templates_no_empty_flow_summary(
        self, template_fn_name: str
    ) -> None:
        import app.services.business_answer_service as svc
        fn = getattr(svc, template_fn_name)
        answer = fn()
        assert "智能体已接收请求" not in answer
        assert "协同分析完成" not in answer
        assert "系统调度了" not in answer


# ══════════════════════════════════════════════════════════════════
# 本地知识答案生成测试 — 离线可用，不依赖 LLM
# ══════════════════════════════════════════════════════════════════

# 验收示例问题
_EXAMPLE_KNOWLEDGE_QUESTION = (
    "基于振动、温度等传感器数据预测设备剩余寿命时，如何动态设定报警阈值以减少误报与漏报？"
    "请提出一种结合统计过程控制与深度学习的自适应阈值方法。"
)


class TestLocalKnowledgeAnswer:
    """验证 _generate_local_knowledge_answer 离线生成解释型答案。"""

    def test_example_question_generates_answer(self) -> None:
        """验收：示例问题必须生成非空答案。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert answer is not None, "示例问题应生成答案"
        assert len(answer) > 100, "答案不应过短"

    @pytest.mark.parametrize("keyword", [
        "SPC",
        "EWMA",
        "LSTM",
        "Transformer",
        "误报",
        "漏报",
        "自适应阈值",
        "统计过程控制",
        "深度学习",
    ])
    def test_example_answer_contains_key_terms(self, keyword: str) -> None:
        """验收：答案必须包含关键技术术语。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert answer is not None
        assert keyword.lower() in answer.lower(), (
            f"答案中未找到关键词: {keyword}"
        )

    def test_example_answer_has_structured_sections(self) -> None:
        """验收：答案包含结构化分段。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert answer is not None
        # 预测性维护模板使用这些段落标题
        sections = ["方案概述", "方法步骤", "注意事项与风险控制"]
        for section in sections:
            assert section in answer, f"缺少段落: {section}"
        # 六步方法步骤
        for step_title in [
            "数据基线建模",
            "SPC 动态控制限",
            "深度学习趋势预测",
            "阈值自适应修正",
            "报警决策",
            "落地建议",
        ]:
            assert step_title in answer, f"缺少步骤: {step_title}"

    def test_no_domain_match_returns_none(self) -> None:
        """无领域匹配时返回 None（不回退到无意义文本）。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer("今天天气不错")
        assert answer is None

    def test_predictive_maintenance_template_has_six_steps(self) -> None:
        """验收：预测性维护模板包含完整 6 步方案。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert answer is not None
        # 6 步编号
        for i in range(1, 7):
            assert f"{i}. " in answer, f"缺少第{i}步"

    @pytest.mark.parametrize("content_keyword", [
        # 公式
        "Upper_t", "Lower_t", "e_t", "Threshold_t", "k_t",
        "μ_t", "σ_t",
        # 报警等级
        "提示", "预警", "严重",
        # 具体方法
        "滞后报警", "多传感器关联异常",
        # 实施细节
        "冷启动", "反馈闭环", "分设备建模", "渐进式部署",
        # 深度学习细节
        "X_hat", "MAE", "MSE",
        # SPC 细节
        "CUSUM", "EWMA",
        # 修正参数
        "α", "β", "γ",
        # 设备类型
        "CNC", "SHAP",
    ])
    def test_predictive_maintenance_content_richness(self, content_keyword: str) -> None:
        """验收：答案包含丰富的技术细节。"""
        from app.services.orchestrator import _generate_local_knowledge_answer
        answer = _generate_local_knowledge_answer(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert answer is not None
        assert content_keyword in answer, (
            f"答案中未找到内容: {content_keyword}"
        )

    def test_predictive_maintenance_template_trigger(self) -> None:
        """验收：_should_use_predictive_maintenance_template 正确触发。"""
        from app.services.orchestrator import _detect_knowledge_domains
        from app.services.business_answer_service import (
            _should_use_predictive_maintenance_template,
        )
        domains = _detect_knowledge_domains(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert _should_use_predictive_maintenance_template(domains) is True

    def test_spc_only_question_uses_generic_template(self) -> None:
        """仅 SPC 问题使用通用模板（不触发预测性维护专用模板）。"""
        from app.services.orchestrator import (
            _detect_knowledge_domains,
            _generate_local_knowledge_answer,
        )
        from app.services.business_answer_service import (
            _should_use_predictive_maintenance_template,
        )
        text = "请解释统计过程控制SPC的基本原理和控制限计算方法"
        domains = _detect_knowledge_domains(text)
        # 虽然命中 spc，但缺少 sensor + fpfn + threshold
        assert _should_use_predictive_maintenance_template(domains) is False
        answer = _generate_local_knowledge_answer(text)
        assert answer is not None
        # 使用通用模板，不含预测性维护专用结构
        assert "数据基线建模" not in answer

    def test_domain_detection_utility(self) -> None:
        """验收：领域检测工具函数。"""
        from app.services.orchestrator import _detect_knowledge_domains
        domains = _detect_knowledge_domains(_EXAMPLE_KNOWLEDGE_QUESTION)
        assert domains["rul"] is True
        assert domains["spc"] is True
        assert domains["threshold"] is True
        assert domains["deep_learning"] is True
        assert domains["fpfn"] is True
        assert domains["sensor"] is True

    def test_robotics_control_question_generates_local_answer(self) -> None:
        """仓储多机器人混合控制策略问题应生成解释型答案。"""
        from app.services.orchestrator import (
            _detect_knowledge_domains,
            _generate_local_knowledge_answer,
            _matches_knowledge_question,
        )

        text = (
            "在密集仓储环境中，多台自主移动机器人同时作业时，如何设计一种"
            "融合集中调度与分布式避障的混合控制策略，既保证全局效率又满足实时安全性？"
        )
        domains = _detect_knowledge_domains(text)
        answer = _generate_local_knowledge_answer(text)

        assert _matches_knowledge_question(text) is True
        assert domains["robotics_control"] is True
        assert answer is not None
        assert "集中调度" in answer
        assert "分布式避障" in answer
        assert "时间窗" in answer
        assert "生产调度智能体已接收请求" not in answer


# ══════════════════════════════════════════════════════════════════
# 知识图谱专项测试
# ══════════════════════════════════════════════════════════════════


class TestKnowledgeGraphLocalAnswer:
    """验证知识图谱构建与故障根因推理问题的本地模板。

    对应任务书：从非结构化工艺文档/维修记录中抽取实体关系、
    构建知识图谱并做根因推理 → 离线模式下返回完整技术方案。
    """

    def test_knowledge_graph_question_detected_as_knowledge(self) -> None:
        """知识图谱问题应被识别为知识型问题。"""
        from app.services.orchestrator import _matches_knowledge_question

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        assert _matches_knowledge_question(text) is True

    def test_knowledge_graph_domain_detected(self) -> None:
        """knowledge_graph 领域应被正确命中。"""
        from app.services.orchestrator import _detect_knowledge_domains

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        domains = _detect_knowledge_domains(text)
        assert domains["knowledge_graph"] is True

    def test_knowledge_graph_generates_local_answer(self) -> None:
        """知识图谱问题应生成非空的本地模板答案。"""
        from app.services.orchestrator import _generate_local_knowledge_answer

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        answer = _generate_local_knowledge_answer(text)
        assert answer is not None
        assert len(answer) > 500

    def test_knowledge_graph_answer_contains_method_steps(self) -> None:
        """答案应包含知识图谱构建的六步方法论。"""
        from app.services.orchestrator import _generate_local_knowledge_answer

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        answer = _generate_local_knowledge_answer(text)
        required_steps = [
            "知识图谱", "实体抽取", "关系抽取", "三元组",
            "根因推理", "非结构化", "工艺文档", "维修记录",
        ]
        for step in required_steps:
            assert step in answer, f"Missing: {step}"

    def test_knowledge_graph_answer_contains_concrete_examples(self) -> None:
        """答案应包含具体实体/故障/根因示例（如 CNC-01、轴承磨损）。"""
        from app.services.orchestrator import _generate_local_knowledge_answer

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        answer = _generate_local_knowledge_answer(text)
        concrete_terms = ["CNC-01", "轴承磨损", "主轴", "振动异常"]
        for term in concrete_terms:
            assert term in answer, f"Missing concrete example: {term}"

    def test_knowledge_graph_answer_no_empty_flow_summary(self) -> None:
        """答案不应包含空洞流程摘要。"""
        from app.services.orchestrator import _generate_local_knowledge_answer

        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        answer = _generate_local_knowledge_answer(text)
        assert "智能体已接收请求" not in answer


# ══════════════════════════════════════════════════════════════════
# require_llm=False 离线模式测试
# ══════════════════════════════════════════════════════════════════


class FakeLLMClient:
    """伪造的 LLM 客户端 — 任何调用都应抛出异常。"""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def is_configured(self) -> bool:
        return True

    async def generate_with_system_prompt(
        self, system_prompt: str, user_prompt: str
    ) -> dict:
        self.call_count += 1
        raise ConnectionError("All connection attempts failed")


class TestOfflineBusinessAnswer:
    """验证 require_llm=False 时不调用 LLM，仅使用本地模板。"""

    @pytest.mark.asyncio
    async def test_offline_returns_local_answer(self) -> None:
        """require_llm=False 的业务问题应返回本地答案，不调 LLM。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.business_answer_service import BusinessAnswerService

        fake_llm = FakeLLMClient()
        svc = BusinessAnswerService(llm_client=fake_llm)

        answer = await svc.generate_answer(
            "如何根据库存和BOM判断缺料风险？",
            agent_names=["supply_chain_management"],
            use_llm=False,
        )
        assert answer is not None, "离线模式应返回本地模板答案"
        assert len(answer) > 100
        # 不应包含空洞摘要标记
        assert "智能体已接收请求" not in answer
        # fake LLM 不应被调用
        assert fake_llm.call_count == 0, (
            f"require_llm=False 时不应调用 LLM，但调用了 {fake_llm.call_count} 次"
        )

    @pytest.mark.asyncio
    async def test_offline_all_five_domains(self) -> None:
        """五个业务领域的离线模板均可正常生成。"""
        from app.services.business_answer_service import BusinessAnswerService

        svc = BusinessAnswerService(llm_client=FakeLLMClient())
        questions = [
            ("如何优化排产计划提升产能？", ["production_scheduling"]),
            ("最近缺陷率上升，如何分析根因？", ["quality_inspection"]),
            ("如何判断设备是否需要预测性维护？", ["predictive_maintenance"]),
            ("如何根据BOM和库存计算缺料风险？", ["supply_chain_management"]),
            ("如何优化工艺参数提升良品率？", ["process_parameter_optimization"]),
        ]
        for text, agents in questions:
            answer = await svc.generate_answer(text, agents, use_llm=False)
            assert answer is not None, f"离线应答失败: {text!r}"
            assert len(answer) > 100, (
                f"答案过短 ({len(answer)} 字): {text!r}"
            )
            assert "智能体已接收请求" not in answer

    @pytest.mark.asyncio
    async def test_orchestrator_with_fake_llm_require_llm_false(self) -> None:
        """Orchestrator 注入 FakeLLMClient + require_llm=False → 不调 LLM，返回本地答案。

        这是验收用例的核心：伪造一个会抛出 ConnectionError 的 LLM 客户端，
        注入到 Orchestrator 中，然后以 require_llm=False 发送业务解释型问题。
        必须验证：
        - fake LLM 从未被调用（call_count == 0）
        - 成功返回本地模板答案
        - summary 不包含空洞标记
        - node_feedback 包含"答案综合"节点
        """
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        fake_llm = FakeLLMClient()
        orch = AgentOrchestrator(llm_client=fake_llm)

        text = "如何根据库存、BOM和在途采购判断缺料风险？"
        req = AgentTaskRequest(request_text=text, require_llm=False)
        resp = await orch.execute(req, db=None)

        # 1) fake LLM 不应被调用
        assert fake_llm.call_count == 0, (
            f"require_llm=False 时不应调用 LLM，但调用了 {fake_llm.call_count} 次"
        )

        # 2) 返回本地模板答案（含真实业务内容）
        assert resp.summary, "summary 不应为空"
        assert len(resp.summary) > 100, (
            f"答案过短 ({len(resp.summary)} 字)"
        )
        assert "库" in resp.summary or "缺料" in resp.summary or "BOM" in resp.summary, (
            f"summary 应包含业务答案内容，实际: {resp.summary[:200]}"
        )

        # 3) 不包含空洞流程摘要
        assert "智能体已接收请求" not in resp.summary

        # 4) node_feedback 包含"答案综合"节点
        synthesis_nodes = [
            n for n in resp.node_feedback
            if n.node_id == "answer-synthesis" or n.node_name == "答案综合"
        ]
        assert len(synthesis_nodes) >= 1, (
            f"node_feedback 应包含「答案综合」节点，实际: "
            f"{[n.node_name for n in resp.node_feedback]}"
        )

    @pytest.mark.asyncio
    async def test_orchestrator_with_fake_llm_require_llm_true_falls_back(self) -> None:
        """Orchestrator 注入 FakeLLMClient + require_llm=True → LLM 失败后回退本地模板。

        验证 require_llm=True 时的容错行为：LLM 调用失败（ConnectionError），
        但不应导致整体请求失败，而应回退到本地模板返回可用的答案。
        """
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        fake_llm = FakeLLMClient()
        orch = AgentOrchestrator(llm_client=fake_llm)

        text = "如何根据库存、BOM和在途采购判断缺料风险？"
        req = AgentTaskRequest(request_text=text, require_llm=True)
        resp = await orch.execute(req, db=None)

        # LLM 应被尝试调用过
        assert fake_llm.call_count >= 1, (
            f"require_llm=True 时应尝试调用 LLM，但调用了 {fake_llm.call_count} 次"
        )

        # 即使 LLM 失败，也应回退到本地模板
        assert resp.summary, "summary 不应为空"
        assert len(resp.summary) > 100, (
            f"LLM 失败后回退答案过短 ({len(resp.summary)} 字)"
        )
        assert "智能体已接收请求" not in resp.summary

        # node_feedback 应包含"答案综合"节点
        synthesis_nodes = [
            n for n in resp.node_feedback
            if n.node_id == "answer-synthesis" or n.node_name == "答案综合"
        ]
        assert len(synthesis_nodes) >= 1

    @pytest.mark.asyncio
    async def test_orchestrator_respects_require_llm_false(self) -> None:
        """Orchestrator 在 require_llm=False 时不调用 LLM 且注入答案综合节点。"""
        from unittest.mock import patch

        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()

        # 用 patch 阻止真实 LLM 调用
        with patch.object(
            orch._answer_service, "_try_llm_answer", return_value=None
        ):
            text = "如何根据库存、BOM和在途采购判断缺料风险？"
            req = AgentTaskRequest(request_text=text, require_llm=False)
            resp = await orch.execute(req, db=None)

            # summary 应包含本地模板内容，而非流程摘要
            assert "库" in resp.summary or "缺料" in resp.summary or "BOM" in resp.summary, (
                f"summary 应包含业务答案内容，实际: {resp.summary[:200]}"
            )
            assert "智能体已接收请求" not in resp.summary

            # node_feedback 应包含"答案综合"节点
            synthesis_nodes = [
                n for n in resp.node_feedback
                if n.node_id == "answer-synthesis" or n.node_name == "答案综合"
            ]
            assert len(synthesis_nodes) >= 1, (
                "离线业务问题应有答案综合节点"
            )


# ══════════════════════════════════════════════════════════════════
# 知识答案注入 Orchestrator 集成测试
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorKnowledgeAnswerInjection:
    """通过 Orchestrator.execute() 验证知识答案注入 + 答案综合节点。"""

    @pytest.mark.asyncio
    async def test_knowledge_question_gets_local_answer(self) -> None:
        """知识型问题在离线环境下获得本地模板答案。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text=_EXAMPLE_KNOWLEDGE_QUESTION,
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        # summary 包含技术术语，不再是流程摘要
        assert "协同分析完成" not in resp.summary, (
            "知识型问题的 summary 不应是流程清单"
        )
        assert "SPC" in resp.summary or "统计过程控制" in resp.summary
        assert len(resp.summary) > 100

    @pytest.mark.asyncio
    async def test_knowledge_question_has_answer_synthesis_node(self) -> None:
        """知识型问题的 node_feedback 包含「答案综合」节点。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text=_EXAMPLE_KNOWLEDGE_QUESTION,
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        node_names = [n.node_name for n in resp.node_feedback]
        assert "答案综合" in node_names, (
            f"node_feedback 中应包含「答案综合」节点，实际: {node_names}"
        )
        # 答案综合节点详情包含字数
        synth = next(n for n in resp.node_feedback if n.node_name == "答案综合")
        assert "字" in synth.detail

    @pytest.mark.asyncio
    async def test_normal_question_unchanged(self) -> None:
        """非知识型问题不受影响，summary 为叙事性总结（非流程清单）。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        # 新格式：统一结构化报告，含问题判断、涉及智能体、核心分析等段落
        assert "【问题判断】" in resp.summary
        assert "【涉及智能体】" in resp.summary
        assert "【核心分析】" in resp.summary
        assert "【方法步骤】" in resp.summary
        assert "【落地建议】" in resp.summary
        assert "【风险提醒】" in resp.summary
        assert "质量检测" in resp.summary or "quality_inspection" in resp.summary
        assert "设备预测性维护" in resp.summary or "predictive_maintenance" in resp.summary
        # 不包含旧的流程清单格式和空洞标记
        assert "协同分析完成" not in resp.summary
        assert "系统调度了" not in resp.summary
        assert "智能体已接收请求" not in resp.summary
        # 不应包含答案综合节点（非知识型问题）
        node_names = [n.node_name for n in resp.node_feedback]
        assert "答案综合" not in node_names

    @pytest.mark.asyncio
    async def test_require_llm_false_still_generates_local_answer(self) -> None:
        """require_llm=False 时也能生成本地解释型答案。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="如何设计一个基于深度学习的设备故障预测方法？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert len(resp.summary) > 80
        assert "协同分析完成" not in resp.summary

    @pytest.mark.asyncio
    async def test_knowledge_graph_question_summary_is_real_answer(self) -> None:
        """知识图谱问题 Orchestrator 返回的 summary 必须是完整技术方案。"""
        from app.services.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        text = (
            "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
            "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
        )
        req = AgentTaskRequest(request_text=text, require_llm=False)
        resp = await orch.execute(req, db=None)

        # summary 必须包含技术答案而非流程摘要
        summary = resp.summary
        assert "文档解析" in summary
        assert "实体抽取" in summary
        assert "关系抽取" in summary
        assert "知识图谱" in summary
        assert "根因推理" in summary

        # 必须排除协同流程摘要
        assert "智能体已接收请求" not in summary
        assert "系统调度了" not in summary
        assert "质量检测与缺陷分析" not in summary

        # 答案综合节点必须存在
        assert any(n.node_name == "答案综合" for n in resp.node_feedback)


# ══════════════════════════════════════════════════════════════════
# 知识答案 API 层集成测试
# ══════════════════════════════════════════════════════════════════


class TestAPIKnowledgeAnswer:
    """通过 FastAPI TestClient 验证知识型问题的 API 响应。"""

    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_api_knowledge_question_returns_answer_not_flow_list(self) -> None:
        body = {"request_text": _EXAMPLE_KNOWLEDGE_QUESTION, "require_llm": False}
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # 离线环境下必须生成解释型答案
        assert "协同分析完成" not in data["summary"], (
            "知识型问题不应返回流程清单"
        )
        assert "SPC" in data["summary"] or "统计过程控制" in data["summary"]

    def test_api_knowledge_question_has_synthesis_node(self) -> None:
        body = {"request_text": _EXAMPLE_KNOWLEDGE_QUESTION, "require_llm": False}
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        node_names = [n["node_name"] for n in data["node_feedback"]]
        assert "答案综合" in node_names

    def test_api_normal_question_no_synthesis_node(self) -> None:
        body = {
            "request_text": "质量缺陷率上升，设备振动异常需要维护处理",
            "require_llm": False,
        }
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        node_names = [n["node_name"] for n in data["node_feedback"]]
        assert "答案综合" not in node_names

    def test_api_knowledge_graph_question_summary_is_real_answer(self) -> None:
        """知识图谱问题 summary 必须是完整技术方案，不能是协同流程摘要。"""
        body = {
            "request_text": (
                "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
                "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
            ),
            "require_llm": False,
        }
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200
        data = resp.json()
        summary = data["summary"]

        # 必须包含知识图谱技术内容（本地模板或 LLM 生成均可）
        assert "文档解析" in summary or "NER" in summary or "实体识别" in summary
        assert "实体抽取" in summary or "实体识别" in summary or "信息抽取" in summary
        assert "关系抽取" in summary or "关系分类" in summary
        assert "知识图谱" in summary
        assert "根因推理" in summary

        # 必须排除空洞流程摘要
        assert "系统调度了" not in summary
        assert "智能体已接收请求" not in summary

        # 答案综合节点必须存在
        node_names = [n["node_name"] for n in data["node_feedback"]]
        assert "答案综合" in node_names

    def test_api_knowledge_graph_question_has_synthesis_node(self) -> None:
        """知识图谱问题应包含答案综合节点。"""
        body = {
            "request_text": (
                "如何从非结构化的工艺文档、维修记录中自动抽取实体与关系，"
                "构建面向制造过程的知识图谱？并举例说明如何利用该图谱进行故障根因推理。"
            ),
            "require_llm": False,
        }
        resp = self.client.post("/api/v1/agents/execute", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        node_names = [n["node_name"] for n in data["node_feedback"]]
        assert "答案综合" in node_names


# ══════════════════════════════════════════════════════════════════
# 空洞回答禁止 — validate_summary 单元测试
# ══════════════════════════════════════════════════════════════════


class TestValidateSummary:
    """验证 validate_summary 正确识别空洞/不合格回答。"""

    def test_null_or_empty_is_invalid(self) -> None:
        from app.services.business_answer_service import validate_summary
        is_valid, violations = validate_summary(None)
        assert not is_valid
        assert len(violations) >= 1

        is_valid, violations = validate_summary("")
        assert not is_valid

        is_valid, violations = validate_summary("   ")
        assert not is_valid

    @pytest.mark.parametrize("hollow_text", [
        "智能体已接收请求，请等待处理。",
        "请提供完整数据结构化参数。",
        "建议通过结构化接口传入数据后再试。",
        "系统调度了若干智能体协同分析。",
        "系统调度了3个智能体协同分析该问题。",
        "综合分析完成，建议按优先级处理。",
        "协同分析完成，请查看各智能体输出。",
        "缺少必要参数，无法处理该请求。",
        "请查看各步骤输出，等待处理。",
    ])
    def test_hollow_patterns_rejected(self, hollow_text: str) -> None:
        from app.services.business_answer_service import validate_summary
        is_valid, violations = validate_summary(hollow_text)
        assert not is_valid, f"应拒绝但通过了: {hollow_text!r}"
        hollow_patterns_in_violations = any(
            "禁止短语" in v for v in violations
        )
        assert hollow_patterns_in_violations, (
            f"violations 应包含禁止短语相关条目，实际: {violations}"
        )

    def test_hollow_prefix_with_rich_content_still_rejected(self) -> None:
        """即使后面拼接了足够长、足够多小标题和步骤的内容，
        只要开头是'系统调度了N个智能体…'，也必须拒绝。"""
        from app.services.business_answer_service import validate_summary

        # 模拟真实场景：开头是空洞的系统调度语句，后面拼接了看似完整的模板内容
        rich_tail = (
            "\n\n【方案概述】\n这是一个系统性的技术方案。\n\n"
            "【方法步骤】\n"
            "1. 数据采集与预处理：收集设备振动、温度、电流等传感器数据。\n"
            "2. 建立SPC基准控制限：计算均值μ和标准差σ。\n"
            "3. 构建深度学习退化预测模型：使用LSTM预测RUL。\n"
            "4. 构建自适应阈值：将SPC控制限与深度学习残差结合。\n"
            "5. 降低误报与漏报策略：引入滞后报警机制。\n"
            "6. 实施建议：部署边缘计算和云端模型更新。\n\n"
            "【注意事项】\n- 数据质量监控\n- 冷启动需要30天数据\n"
            "- 阈值漂移需每季度重标定\n- 模型可解释性\n- 人机协同\n"
        ) * 2  # 重复两遍确保足够长

        # 场景1: "系统调度了3个智能体协同分析该问题。" + 长内容
        text1 = "系统调度了3个智能体协同分析该问题。" + rich_tail
        is_valid1, violations1 = validate_summary(text1)
        assert not is_valid1, (
            f"'系统调度了3个智能体...' 开头应被拒绝，但通过了。\n"
            f"violations: {violations1}"
        )
        # 确保是因为空洞模式被拒，而非其他原因
        assert any("禁止短语" in v for v in violations1), (
            f"拒绝原因应包含'禁止短语'，实际: {violations1}"
        )

        # 场景2: "系统调度了2个智能体协同分析该问题。" + 长内容
        text2 = "系统调度了2个智能体协同分析该问题。" + rich_tail
        is_valid2, _ = validate_summary(text2)
        assert not is_valid2, "'系统调度了2个智能体...' 应被拒绝"

        # 场景3: "XX智能体已接收请求" + 长内容
        text3 = "预测性维护智能体已接收请求。" + rich_tail
        is_valid3, _ = validate_summary(text3)
        assert not is_valid3, "'智能体已接收请求' 应被拒绝"

    def test_too_short_is_invalid(self) -> None:
        """中文字符不足 300 字的短文本应被拒绝。"""
        from app.services.business_answer_service import validate_summary
        short_text = "这是一个测试方案。建议优化参数。质量很好。提高效率。"
        is_valid, violations = validate_summary(short_text)
        assert not is_valid
        assert any("中文字符数不足" in v for v in violations)

    def test_no_subheadings_is_invalid(self) -> None:
        """缺少小标题的文本应被拒绝。"""
        from app.services.business_answer_service import validate_summary
        # 构造一段 >300 中文字符但无小标题的文本
        text = (
            "针对您的生产调度问题，建议采用瓶颈优先策略进行排产优化。"
            "首先需要梳理所有待排产订单并标注优先级和交期要求。"
            "其次统计各设备的可用产能并计算负荷率以识别瓶颈工序。"
            "对于负荷率超过百分之八十五的设备，应优先安排生产并建立时间缓冲。"
            "同时应采用EDD规则处理交期紧迫的订单，确保按时交付。"
            "在产能不足时可以采取加班外协或者多班次等临时措施增加产能。"
            "长期来看建议引入APS系统实现自动排程和实时优化。"
            "此外还应建立每日产销协调会机制确保销售生产和采购三方信息同步。"
            "对于插单需求应建立审批流程并评估对已有工单的交期影响。"
            "最后建议每季度审核安全库存水平并根据实际需求波动进行调整。"
            "通过以上措施可以显著提升交期满足率和设备利用率降低拖期风险。" * 3
        )
        is_valid, violations = validate_summary(text)
        assert not is_valid
        assert any("小标题" in v for v in violations)

    def test_quality_template_is_valid(self) -> None:
        """五个专家模板均应通过质量验证。"""
        from app.services.business_answer_service import (
            _generate_production_scheduling_answer,
            _generate_quality_inspection_answer,
            _generate_predictive_maintenance_business_answer,
            _generate_supply_chain_management_answer,
            _generate_process_parameter_optimization_answer,
            validate_summary,
        )
        templates = [
            _generate_production_scheduling_answer(),
            _generate_quality_inspection_answer(),
            _generate_predictive_maintenance_business_answer(),
            _generate_supply_chain_management_answer(),
            _generate_process_parameter_optimization_answer(),
        ]
        for i, answer in enumerate(templates):
            is_valid, violations = validate_summary(answer)
            assert is_valid, (
                f"模板 {i} 未通过验证:\n" + "\n".join(violations)
            )

    def test_knowledge_graph_answer_is_valid(self) -> None:
        from app.services.business_answer_service import (
            _generate_knowledge_graph_answer,
            validate_summary,
        )
        answer = _generate_knowledge_graph_answer()
        is_valid, violations = validate_summary(answer)
        assert is_valid, f"知识图谱模板未通过验证:\n" + "\n".join(violations)

    def test_robotics_control_answer_is_valid(self) -> None:
        from app.services.business_answer_service import (
            _generate_robotics_control_answer,
            validate_summary,
        )
        answer = _generate_robotics_control_answer()
        is_valid, violations = validate_summary(answer)
        assert is_valid, f"机器人控制模板未通过验证:\n" + "\n".join(violations)

    def test_only_field_names_rejected(self) -> None:
        """只列字段名的回答应被疑似检测标记。"""
        from app.services.business_answer_service import validate_summary
        text = (
            "字段1：订单ID\n字段2：产品名称\n字段3：数量\n"
            "字段4：交期\n字段5：设备ID\n字段6：开工时间\n"
            "字段7：完工时间\n字段8：优先级\n字段9：状态\n"
            "字段10：备注\n字段11：负责人\n字段12：审批人\n"
        ) * 2  # 凑够一定长度
        is_valid, violations = validate_summary(text)
        # 应该因为缺少业务关键词或其他原因不通过
        assert not is_valid

    def test_data_request_only_rejected(self) -> None:
        """只要求用户补数据的回答应被拒绝。"""
        from app.services.business_answer_service import validate_summary
        text = (
            "请提供完整的生产排产数据，包括订单信息、设备产能、工艺路线等。"
            "请传入详细的参数信息以便系统进行分析。"
            "请提供完整数据后重新提交请求。"
            "请填写所有必填字段后再次尝试。"
        ) * 3
        is_valid, violations = validate_summary(text)
        assert not is_valid
        assert any("补数据" in v for v in violations)

    def test_count_chinese_chars(self) -> None:
        from app.services.business_answer_service import _count_chinese_chars
        assert _count_chinese_chars("你好世界") == 4
        assert _count_chinese_chars("hello world") == 0
        assert _count_chinese_chars("中文Mixed英文") == 4

    def test_count_subheadings(self) -> None:
        from app.services.business_answer_service import _count_subheadings
        text = (
            "【方案概述】\n这是概述内容。\n"
            "【方法步骤】\n1. 第一步\n2. 第二步\n"
            "【实施建议】\n- 建议一\n- 建议二\n"
        )
        count = _count_subheadings(text)
        assert count >= 5, f"应至少有 5 个小标题/段落，实际: {count}"

    def test_count_specific_steps(self) -> None:
        from app.services.business_answer_service import _count_specific_steps
        text = (
            "1. 数据采集\n2. 特征提取\n3. 模型训练\n"
            "- 使用LSTM模型\n- 使用Transformer模型\n"
            "(a) 评估准确率\n(b) 评估召回率\n"
        )
        count = _count_specific_steps(text)
        assert count >= 7, f"应至少有 7 个步骤/建议，实际: {count}"


# ══════════════════════════════════════════════════════════════════
# 空洞回答 Orchestrator 集成测试
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorHollowAnswerRejection:
    """验证 Orchestrator 在遇到空洞 LLM 回答时不会注入到 summary。"""

    class _HollowLLMClient:
        """返回空洞内容的伪造 LLM 客户端。"""

        def __init__(self) -> None:
            self.call_count = 0

        @property
        def is_configured(self) -> bool:
            return True

        async def generate_with_system_prompt(
            self, system_prompt: str, user_prompt: str
        ) -> dict:
            self.call_count += 1
            return {"content": "综合分析完成，建议按优先级处理。系统调度了若干智能体协同分析，请查看各步骤输出。"}

    @pytest.mark.asyncio
    async def test_hollow_llm_answer_not_injected(self) -> None:
        """LLM 返回空洞回答时，不应覆盖 summary（保留智能体原始分析结果）。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        fake_llm = self._HollowLLMClient()
        orch = AgentOrchestrator(llm_client=fake_llm)

        text = "如何根据库存、BOM和在途采购判断缺料风险？"
        req = AgentTaskRequest(request_text=text, require_llm=True)
        resp = await orch.execute(req, db=None)

        # LLM 被调用过
        assert fake_llm.call_count >= 1

        # summary 不应被空洞 LLM 回答覆盖
        assert "综合分析完成" not in resp.summary
        assert "系统调度了" not in resp.summary
        assert "智能体已接收请求" not in resp.summary

        # 应该回退到本地模板或保留智能体原始分析
        assert len(resp.summary) > 50, (
            f"summary 不应为空或过短，实际: {resp.summary[:200]}"
        )

    @pytest.mark.asyncio
    async def test_offline_knowledge_question_not_hollow(self) -> None:
        """require_llm=False 的知识型问题，summary 不能是空洞内容。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()

        # 测试所有典型知识问题
        questions = [
            "如何根据库存、BOM和在途采购判断缺料风险？",
            "如何优化排产计划提升产能？",
            "最近缺陷率上升，如何分析根因？",
            "如何判断设备是否需要预测性维护？",
            "如何优化工艺参数提升良品率？",
        ]
        for q in questions:
            req = AgentTaskRequest(request_text=q, require_llm=False)
            resp = await orch.execute(req, db=None)

            # 检查禁止短语
            hollow_markers = [
                "智能体已接收请求", "请提供完整数据",
                "系统调度了", "综合分析完成",
                "建议按优先级处理",
            ]
            for marker in hollow_markers:
                assert marker not in resp.summary, (
                    f"问题 {q!r} 的 summary 包含禁止短语: {marker}\n"
                    f"summary: {resp.summary[:300]}"
                )

            # 应有实质性内容
            assert len(resp.summary) > 100, (
                f"问题 {q!r} 的 summary 过短: {len(resp.summary)} 字"
            )


# ══════════════════════════════════════════════════════════════════
# generate_answer 在无合格答案时返回 None 的测试
# ══════════════════════════════════════════════════════════════════


class TestGenerateAnswerReturnsNoneWhenInvalid:
    """验证 BusinessAnswerService.generate_answer 不会返回不合格文本。"""

    @pytest.mark.asyncio
    async def test_non_business_question_returns_none_offline(self) -> None:
        """非业务问题的 generate_answer 应返回 None，不返回不合格兜底文本。"""
        from app.services.business_answer_service import BusinessAnswerService

        svc = BusinessAnswerService(llm_client=None)
        # "今天天气不错" 不匹配任何业务领域也不匹配知识领域
        answer = await svc.generate_answer(
            "今天天气不错",
            agent_names=["production_scheduling"],
            use_llm=False,
        )
        # 应返回 None 而非空洞的兜底文本
        assert answer is None, (
            f"非业务问题应返回 None，实际返回: {answer!r}"
        )

    @pytest.mark.asyncio
    async def test_single_keyword_but_no_template_match_returns_none(
        self,
    ) -> None:
        """只有一个弱关键词但模板不匹配时，不应返回不合格文本。"""
        from app.services.business_answer_service import BusinessAnswerService

        svc = BusinessAnswerService(llm_client=None)
        # "请帮我看看" 有 "请" 可能触发解释型问法，但不匹配任何业务领域
        answer = await svc.generate_answer(
            "请帮我看看",
            agent_names=["production_scheduling"],
            use_llm=False,
        )
        # 不应返回"智能体已接收请求"之类文本
        if answer is not None:
            assert "智能体已接收请求" not in answer
            assert "系统调度了" not in answer


# ══════════════════════════════════════════════════════════════════
# 协同 summary 质量验证 — 禁止 RAG 证据、禁止提供数据步骤
# ══════════════════════════════════════════════════════════════════


class TestCollaborativeSummaryQuality:
    """验证协同 summary 不包含原始 RAG 证据、不包含提供数据类步骤。"""

    @pytest.mark.asyncio
    async def test_summary_has_all_seven_sections(self) -> None:
        """协同 summary 必须包含全部 7 个段落。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"

        sections = [
            "【问题判断】", "【涉及智能体】", "【核心分析】",
            "【方法步骤】", "【落地建议】", "【风险提醒】",
            "【后续需要的数据】",
        ]
        for section in sections:
            assert section in resp.summary, f"缺少段落: {section}"

        # agent_chain 和 node_feedback 仍然存在
        assert len(resp.agent_chain) >= 2
        assert len(resp.node_feedback) >= 6

    @pytest.mark.asyncio
    async def test_summary_no_raw_knowledge_evidence(self) -> None:
        """协同 summary 不得包含 [knowledge: 原始 RAG 证据。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert "[knowledge:" not in resp.summary, (
            f"summary 不应包含原始 RAG 证据标记\n"
            f"summary: {resp.summary[:500]}"
        )

    @pytest.mark.asyncio
    async def test_summary_no_cross_session_memory(self) -> None:
        """协同 summary 不得包含"跨会话记忆"。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert "跨会话记忆" not in resp.summary

    @pytest.mark.asyncio
    async def test_method_steps_no_data_provide_requests(self) -> None:
        """【方法步骤】不得包含"提供质检批次信息"等字段收集内容。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        # 提取【方法步骤】段落
        import re
        steps_section = ""
        match = re.search(
            r'【方法步骤】\n(.*?)(?=\n【|$)', resp.summary, re.DOTALL
        )
        if match:
            steps_section = match.group(1)

        # 禁止在方法步骤中出现这些字段收集关键词
        forbidden_in_steps = [
            "inspection_batch", "inspection_items", "defect_records",
            "equipment", "context", "historical_defects",
            "提供质检", "提供排产", "提供设备", "提供数据",
            "请传入", "请补充",
        ]
        for forbidden in forbidden_in_steps:
            assert forbidden not in steps_section, (
                f"方法步骤包含禁止的字段收集内容: {forbidden}\n"
                f"步骤内容: {steps_section[:300]}"
            )

    @pytest.mark.asyncio
    async def test_method_steps_has_at_least_five_steps(self) -> None:
        """【方法步骤】至少包含 5 条真正的业务处理步骤。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        import re
        steps_section = ""
        match = re.search(
            r'【方法步骤】\n(.*?)(?=\n【|$)', resp.summary, re.DOTALL
        )
        if match:
            steps_section = match.group(1)

        # 计数编号步骤 1. 2. 3. ...
        numbered_steps = re.findall(r'^\s*\d+\.\s', steps_section, re.MULTILINE)
        assert len(numbered_steps) >= 5, (
            f"方法步骤不足 5 条: 仅 {len(numbered_steps)} 条\n"
            f"内容: {steps_section[:400]}"
        )

    @pytest.mark.asyncio
    async def test_data_requests_go_to_data_needs_not_steps(self) -> None:
        """提供数据类的内容应出现在【后续需要的数据】而非【方法步骤】。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        # 使用不触发知识问答注入的协同场景问题
        req = AgentTaskRequest(
            request_text="排产前需要检查供应链库存是否充足，避免缺料影响交期",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        # 【后续需要的数据】段落应存在且有内容
        assert "【后续需要的数据】" in resp.summary

        # 如果"提供"出现在 summary 中，它应该在数据需求段落而非方法步骤
        import re
        data_section = ""
        match = re.search(
            r'【后续需要的数据】\n(.*?)(?=\n【|$)', resp.summary, re.DOTALL
        )
        if match:
            data_section = match.group(1)

        # "提供"类关键词应只在数据段落中
        if "提供" in resp.summary:
            steps_section = ""
            match2 = re.search(
                r'【方法步骤】\n(.*?)(?=\n【|$)', resp.summary, re.DOTALL
            )
            if match2:
                steps_section = match2.group(1)
            # 方法步骤中不应有"提供数据"类内容
            assert "提供" not in steps_section or "提供" in data_section, (
                "'提供'类内容应放在【后续需要的数据】中"
            )

    @pytest.mark.asyncio
    async def test_collaborative_three_agent_summary_quality(self) -> None:
        """三智能体全链路协同 summary 也通过所有质量检查。"""
        from app.services.orchestrator import AgentOrchestrator
        from app.schemas.agent import AgentTaskRequest

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动传感器报警，"
                         "需要优化工艺参数来改善良品率",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        assert resp.execution_mode == "collaborative"

        # 7 段落全部存在
        for section in [
            "【问题判断】", "【涉及智能体】", "【核心分析】",
            "【方法步骤】", "【落地建议】", "【风险提醒】",
            "【后续需要的数据】",
        ]:
            assert section in resp.summary, f"三智能体缺段落: {section}"

        # 禁令检查
        assert "[knowledge:" not in resp.summary
        assert "跨会话记忆" not in resp.summary
        assert "系统调度了" not in resp.summary
        assert "智能体已接收请求" not in resp.summary


# ══════════════════════════════════════════════════════════════════
# 五大智能体自然语言业务问题测试
# ══════════════════════════════════════════════════════════════════


class TestBusinessAgentNaturalLanguageQuestions:
    """每个智能体至少 2 个自然语言业务问题，通过 Orchestrator 端到端测试。

    每个测试断言：
    - summary 不是空洞流程
    - 不包含"智能体已接收请求"作为主答案
    - 包含该领域关键业务词
    - 长度足够（>100 字）
    - node_feedback 存在
    - next_actions 存在
    """

    @staticmethod
    def _assert_quality(resp, domain_keywords: list[str]) -> None:
        """统一质量断言。"""
        # 不包含空洞标记
        hollow_markers = [
            "智能体已接收请求", "请提供完整数据",
            "系统调度了", "协同分析完成",
            "建议按优先级处理",
        ]
        for marker in hollow_markers:
            assert marker not in resp.summary, (
                f"summary 包含禁止短语: {marker}"
            )

        # 长度足够
        assert len(resp.summary) > 100, (
            f"summary 过短: {len(resp.summary)} 字"
        )

        # 包含至少一个领域关键词
        found = [kw for kw in domain_keywords if kw in resp.summary]
        assert len(found) >= 1, (
            f"summary 未包含领域关键词 {domain_keywords}，"
            f"实际: {resp.summary[:200]}"
        )

        # node_feedback 存在
        assert len(resp.node_feedback) >= 1, "node_feedback 不应为空"

        # next_actions 存在
        assert len(resp.next_actions) >= 1, "next_actions 不应为空"

    # ── 1. 生产调度优化 ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_production_scheduling_delivery_conflict(self) -> None:
        """订单交期集中 + 产能不足 → 生产调度优化方案。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="订单交期集中在本周，但关键设备产能不足，"
                         "如何优化生产排程？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "排产", "调度", "工单", "产能", "交期", "瓶颈",
            "EDD", "SPT", "CR", "排程",
        ])

        # 业务特定检查
        assert any(kw in resp.summary for kw in [
            "排产", "排程", "调度", "工单",
        ]), f"生产调度方案应包含排产相关术语: {resp.summary[:300]}"

    @pytest.mark.asyncio
    async def test_production_scheduling_multi_line_coordination(self) -> None:
        """多产线多设备多工序协调排程。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="多条产线同时有紧急订单，如何协调多设备多工序"
                         "避免交期冲突？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "排产", "调度", "工单", "产能", "交期", "瓶颈", "设备",
        ])

        assert "产线" in resp.summary or "设备" in resp.summary or "工序" in resp.summary

    # ── 2. 质量检测与缺陷分析 ──────────────────────────────

    @pytest.mark.asyncio
    async def test_quality_inspection_defect_rate_rise(self) -> None:
        """缺陷率上升 + 尺寸偏差/粗糙度异常 → 根因分析。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="最近批次缺陷率上升，主要缺陷为尺寸偏差和表面粗糙度异常，"
                         "如何分析根因？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "质量", "缺陷", "根因", "尺寸", "粗糙度", "人机料法环",
            "8D", "Cpk", "检测",
        ])

        assert any(kw in resp.summary for kw in [
            "尺寸", "粗糙度", "缺陷", "质量",
        ]), f"质量分析应包含缺陷相关术语: {resp.summary[:300]}"

    @pytest.mark.asyncio
    async def test_quality_inspection_welding_defects(self) -> None:
        """焊接裂纹和气孔 → 4M1E 根因定位。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="焊接工序出现裂纹和气孔缺陷，如何用人机料法环方法"
                         "定位根本原因？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "质量", "缺陷", "根因", "裂纹", "气孔", "人机料法环",
            "焊接", "检测",
        ])

        assert any(kw in resp.summary for kw in [
            "裂纹", "气孔", "焊接", "缺陷",
        ])

    # ── 3. 设备预测性维护 ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_predictive_maintenance_rul_and_threshold(self) -> None:
        """振动/温度/电流数据 → RUL 预测 + 动态报警阈值。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="基于振动、温度、电流数据，如何预测设备剩余寿命"
                         "并动态设置报警阈值？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "振动", "温度", "电流", "RUL", "剩余寿命", "报警",
            "阈值", "预测", "维护", "SPC", "EWMA", "LSTM",
        ])

        assert any(kw in resp.summary for kw in [
            "RUL", "剩余寿命", "预测", "报警",
        ])

    @pytest.mark.asyncio
    async def test_predictive_maintenance_cnc_spindle(self) -> None:
        """CNC 主轴振动升高 → 判断是否需维护 + 生成工单。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="CNC主轴振动值持续升高，如何判断是否需要立即维护"
                         "并生成维护工单？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "振动", "维护", "故障", "主轴", "工单", "报警",
            "预测", "传感器", "轴承",
        ])

        assert any(kw in resp.summary for kw in [
            "振动", "维护", "主轴", "轴承",
        ])

    # ── 4. 供应链协同管理 ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_supply_chain_shortage_risk(self) -> None:
        """生产计划增加 → 库存/BOM/在途采购判断缺料风险。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="生产计划增加后，如何根据库存、BOM和在途采购"
                         "判断缺料风险？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "库存", "采购", "BOM", "缺料", "物料", "供应商",
            "供应链", "安全库存", "MRP",
        ])

        assert any(kw in resp.summary for kw in [
            "库存", "采购", "BOM", "缺料", "物料",
        ])

    @pytest.mark.asyncio
    async def test_supply_chain_supplier_delay(self) -> None:
        """供应商交付延迟 → 影响评估 + 应对方案。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="关键物料供应商交付延迟，如何评估对生产的影响"
                         "并制定应对方案？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "库存", "采购", "缺料", "物料", "供应商", "交付",
            "供应链", "应对", "风险",
        ])

        assert any(kw in resp.summary for kw in [
            "供应商", "交付", "物料", "库存",
        ])

    # ── 5. 工艺参数优化 ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_process_optimization_parameter_yield(self) -> None:
        """历史数据+质量反馈 → 优化温度/压力/速度参数。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="如何根据历史生产数据和质量反馈优化温度、压力、"
                         "速度等工艺参数？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "工艺", "参数", "温度", "压力", "速度", "优化",
            "良品率", "DOE", "响应面", "SPC", "Cpk",
        ])

        assert any(kw in resp.summary for kw in [
            "温度", "压力", "参数", "工艺优化",
        ])

    @pytest.mark.asyncio
    async def test_process_optimization_injection_molding(self) -> None:
        """注塑成型良品率下降 → 参数-缺陷关系分析 + 最优参数组合。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="注塑成型良品率持续下降，如何分析参数与缺陷的关系"
                         "并找到最优参数组合？",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        self._assert_quality(resp, [
            "工艺", "参数", "优化", "良品率", "缺陷",
            "DOE", "贝叶斯", "响应面", "注塑",
        ])

        assert any(kw in resp.summary for kw in [
            "参数", "良品率", "工艺", "优化",
        ])


# ══════════════════════════════════════════════════════════════════
# 独立智能体端点 summary 空洞兜底测试
# ══════════════════════════════════════════════════════════════════


class TestSingleAgentEndpointSummaryQuality:
    """验证 5 个独立智能体指定调用不再返回空洞 summary。

    每个测试通过 AgentTaskRequest(agent_name=...) 指定智能体，
    验证 Orchestrator 的兜底质量门将空洞流程话术替换为业务分析模板。
    """

    REQUIRED_FIELDS = [
        "trace_id", "request_text", "execution_mode",
        "detected_scenes", "agent_name", "summary",
        "decision", "evidence", "next_actions", "node_feedback",
    ]

    @staticmethod
    def _assert_quality(resp, business_keywords: list[str]) -> None:
        """统一质量断言：不空洞、有内容、字段完整、节点存在。"""
        # 1. 不含空洞话术
        hollow_markers = [
            "已接收请求", "建议通过结构化接口",
            "请提供完整", "传入完整",
        ]
        for marker in hollow_markers:
            assert marker not in resp.summary, (
                f"summary 包含禁止短语: {marker}\n"
                f"summary: {resp.summary[:200]}"
            )

        # 2. 长度 ≥ 120
        assert len(resp.summary) >= 120, (
            f"summary 过短: {len(resp.summary)} 字"
        )

        # 3. 包含至少一个业务关键词
        found = [kw for kw in business_keywords if kw in resp.summary]
        assert len(found) >= 1, (
            f"summary 未包含业务关键词 {business_keywords}，"
            f"实际: {resp.summary[:200]}"
        )

        # 4. node_feedback 包含"答案综合"节点
        synthesis_nodes = [
            n for n in resp.node_feedback
            if n.node_id == "answer-synthesis" or n.node_name == "答案综合"
        ]
        assert len(synthesis_nodes) >= 1, (
            f"node_feedback 应包含「答案综合」节点，"
            f"实际: {[n.node_name for n in resp.node_feedback]}"
        )

        # 5. 所有必填字段存在
        for field in TestSingleAgentEndpointSummaryQuality.REQUIRED_FIELDS:
            assert hasattr(resp, field) or field in resp.__dict__ or field in (
                resp.model_dump() if hasattr(resp, 'model_dump') else {}
            ), f"缺少字段: {field}"

    # ── 生产调度 ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_production_scheduling_no_longer_hollow(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="下周3个工单面临交期风险，CNC设备产能利用率92%，"
                         "请分析瓶颈并提出排产优化建议。",
            agent_name="production_scheduling",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        self._assert_quality(resp, [
            "排产", "调度", "工单", "产能", "交期", "瓶颈",
            "EDD", "SPT", "CR", "排程", "负荷率",
        ])

    # ── 质量检测 ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_quality_inspection_no_longer_hollow(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="最近批次缺陷率上升至8%，主要缺陷为尺寸偏差和"
                         "表面粗糙度，请分析根因并给出改进建议。",
            agent_name="quality_inspection",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        self._assert_quality(resp, [
            "质量", "缺陷", "根因", "尺寸", "粗糙度",
            "人机料法环", "8D", "Cpk", "检测", "改进",
        ])

    # ── 预测性维护 ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_predictive_maintenance_no_longer_hollow(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="设备振动和温度持续升高，请分析故障风险、"
                         "可能原因和维护建议。",
            agent_name="predictive_maintenance",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        self._assert_quality(resp, [
            "振动", "温度", "维护", "故障", "预测",
            "传感器", "轴承", "RUL", "报警", "阈值",
        ])

    # ── 供应链 ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_supply_chain_no_longer_hollow(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="关键物料库存低于安全库存，供应商交付延迟，"
                         "请分析缺料风险和采购建议。",
            agent_name="supply_chain_management",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        self._assert_quality(resp, [
            "库存", "采购", "缺料", "物料", "供应商",
            "供应链", "安全库存", "BOM", "交付", "风险",
        ])

    # ── 工艺优化 ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_process_parameter_no_longer_hollow(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="注塑产品良品率下降，温度、压力和保压时间波动明显，"
                         "请分析工艺参数优化方案。",
            agent_name="process_parameter_optimization",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)
        self._assert_quality(resp, [
            "工艺", "参数", "优化", "良品率", "温度",
            "压力", "DOE", "响应面", "SPC", "Cpk",
        ])
