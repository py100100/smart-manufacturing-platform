"""集成测试 — 覆盖 5 智能体路由、错误输入、未知场景、多智能体协同、端到端流水线。"""

from __future__ import annotations

import pytest

AGENT_NAMES = [
    "production_scheduling",
    "quality_inspection",
    "predictive_maintenance",
    "supply_chain_management",
    "process_parameter_optimization",
]

API_PREFIX = "/api/v1/agents"


# ══════════════════════════════════════════════════════════════════
# 错误输入处理
# ══════════════════════════════════════════════════════════════════


class TestErrorInputs:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_empty_request_text_rejected(self) -> None:
        resp = self.client.post(f"{API_PREFIX}/execute", json={"request_text": ""})
        assert resp.status_code == 422

    def test_too_short_request_text_rejected(self) -> None:
        resp = self.client.post(f"{API_PREFIX}/execute", json={"request_text": "ab"})
        assert resp.status_code == 422

    def test_missing_require_llm_defaults(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "分析质量缺陷原因"},
        )
        # 缺少 require_llm → 默认 True → 应正常工作
        assert resp.status_code == 200

    def test_invalid_agent_name_in_body_rejected(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "测试请求", "agent_name": "nonexistent_agent"},
        )
        assert resp.status_code == 422

    def test_invalid_json_rejected(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            content=b"not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code >= 400

    def test_long_request_text_accepted(self) -> None:
        text = "分析质量缺陷原因并优化排产计划 " * 50  # ~1000 chars
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": text[:1900], "require_llm": False},
        )
        assert resp.status_code == 200

    def test_special_characters_in_text_accepted(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={
                "request_text": "分析 CNC-001 设备的振动(加速度>12mm/s²)&温度异常，需要紧急维护！",
                "require_llm": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # 特殊字符不影响解析；该文本命中多个场景关键词，可能触发协同
        assert data["execution_mode"] in ("single", "collaborative")

    def test_extra_fields_in_body_ignored(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={
                "request_text": "分析质量缺陷",
                "require_llm": False,
                "extra_field": "should be ignored",
            },
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# 5 智能体路由 — 通过统一 /execute 端点
# ══════════════════════════════════════════════════════════════════


class TestFiveAgentRoutingViaExecute:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, text: str) -> dict:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": text, "require_llm": False},
        )
        assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text}"
        return resp.json()

    def test_production_scheduling_scene_routes(self) -> None:
        data = self._post("请优化排产计划提升产能，解决瓶颈问题")
        assert data["agent_name"] == "production_scheduling"

    def test_quality_inspection_scene_routes(self) -> None:
        data = self._post("分析最近批次质量缺陷和不良率根因")
        assert data["agent_name"] == "quality_inspection"

    def test_predictive_maintenance_scene_routes(self) -> None:
        data = self._post("设备振动传感器读数异常，需要预测性维护")
        assert data["agent_name"] == "predictive_maintenance"

    def test_supply_chain_management_scene_routes(self) -> None:
        data = self._post("供应链库存缺料风险分析，采购订单延期")
        assert data["agent_name"] == "supply_chain_management"

    def test_process_parameter_optimization_scene_routes(self) -> None:
        data = self._post("优化热处理工艺温度和压力参数提升良品率")
        assert data["agent_name"] == "process_parameter_optimization"

    def test_each_route_returns_complete_response(self) -> None:
        queries = {
            "production_scheduling": "优化排产计划产能",
            "quality_inspection": "分析质量缺陷根因",
            "predictive_maintenance": "设备振动需要维护",
            "supply_chain_management": "供应链库存缺料分析",
            "process_parameter_optimization": "优化工艺参数温度",
        }
        for agent_name, query in queries.items():
            data = self._post(query)
            assert data["agent_name"] == agent_name, f"Expected {agent_name}, got {data['agent_name']}"
            assert data["execution_mode"] == "single"
            assert len(data["node_feedback"]) >= 3
            assert len(data["agent_chain"]) == 1
            assert "closure" in data
            assert len(data["closure"]["reports"]) >= 1
            assert len(data["closure"]["action_items"]) >= 1


# ══════════════════════════════════════════════════════════════════
# 5 智能体路由 — 通过按名 /{agent_name}/execute 端点
# ══════════════════════════════════════════════════════════════════


class TestFiveAgentRoutingViaPerAgent:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, agent_name: str, text: str = "测试请求") -> dict:
        resp = self.client.post(
            f"{API_PREFIX}/{agent_name}/execute",
            json={"request_text": text, "require_llm": False},
        )
        assert resp.status_code == 200, f"{agent_name}: {resp.status_code} {resp.text}"
        return resp.json()

    def test_per_agent_production_scheduling(self) -> None:
        data = self._post("production_scheduling", "排产优化")
        assert data["agent_name"] == "production_scheduling"
        assert data["execution_mode"] == "single"

    def test_per_agent_quality_inspection(self) -> None:
        data = self._post("quality_inspection", "质量分析")
        assert data["agent_name"] == "quality_inspection"

    def test_per_agent_predictive_maintenance(self) -> None:
        data = self._post("predictive_maintenance", "设备维护")
        assert data["agent_name"] == "predictive_maintenance"

    def test_per_agent_supply_chain_management(self) -> None:
        data = self._post("supply_chain_management", "库存分析")
        assert data["agent_name"] == "supply_chain_management"

    def test_per_agent_process_parameter_optimization(self) -> None:
        data = self._post("process_parameter_optimization", "参数优化")
        assert data["agent_name"] == "process_parameter_optimization"

    def test_per_agent_invalid_name_rejected(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/bad_agent_name/execute",
            json={"request_text": "测试", "require_llm": False},
        )
        assert resp.status_code == 422

    def test_per_agent_all_return_closure(self) -> None:
        for name in AGENT_NAMES:
            data = self._post(name, f"{name} 测试请求")
            assert "closure" in data, f"{name}: 缺少 closure"
            c = data["closure"]
            assert "alerts" in c
            assert "work_orders" in c
            assert "reports" in c
            assert "action_items" in c
            assert len(c["reports"]) >= 1


# ══════════════════════════════════════════════════════════════════
# 未知场景
# ══════════════════════════════════════════════════════════════════


class TestUnknownSceneFallback:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_unknown_defaults_to_production_scheduling(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "今天天气真不错", "require_llm": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "production_scheduling"
        assert data["execution_mode"] == "single"

    def test_english_text_defaults_gracefully(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={
                "request_text": "What is the weather like today?",
                "require_llm": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_mode"] == "single"

    def test_numbers_only_text_handled(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "12345 67890", "require_llm": False},
        )
        assert resp.status_code == 200

    def test_symbols_only_text_handled(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "!@#$%^&*()", "require_llm": False},
        )
        assert resp.status_code == 200

    def test_default_route_returns_complete_response(self) -> None:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": "没有匹配的场景", "require_llm": False},
        )
        data = resp.json()
        assert data["agent_name"] == "production_scheduling"
        assert len(data["node_feedback"]) >= 3
        assert "closure" in data


# ══════════════════════════════════════════════════════════════════
# 多智能体协同场景
# ══════════════════════════════════════════════════════════════════


class TestCollaborativeScenarios:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, text: str) -> dict:
        resp = self.client.post(
            f"{API_PREFIX}/execute",
            json={"request_text": text, "require_llm": False},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    # ── 双智能体链 ──────────────────────────────────────

    def test_quality_and_maintenance_collaborative(self) -> None:
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")
        assert data["execution_mode"] == "collaborative"
        chain = [s["agent_name"] for s in data["agent_chain"]]
        assert "quality_inspection" in chain
        assert "predictive_maintenance" in chain
        assert len(chain) == 2

    def test_supply_chain_and_scheduling_collaborative(self) -> None:
        data = self._post("排产前需要检查供应链库存是否充足，避免缺料影响交期")
        assert data["execution_mode"] == "collaborative"
        chain = [s["agent_name"] for s in data["agent_chain"]]
        assert chain[0] == "supply_chain_management"
        assert chain[1] == "production_scheduling"

    def test_quality_and_process_collaborative(self) -> None:
        data = self._post("质量良率低于目标，需要优化工艺温度和压力参数来提升")
        assert data["execution_mode"] == "collaborative"
        chain = [s["agent_name"] for s in data["agent_chain"]]
        assert "quality_inspection" in chain
        assert "process_parameter_optimization" in chain

    def test_maintenance_and_scheduling_collaborative(self) -> None:
        data = self._post("设备故障需要维护，同时需要调整排产计划应对产能损失")
        assert data["execution_mode"] == "collaborative"
        chain = [s["agent_name"] for s in data["agent_chain"]]
        assert "predictive_maintenance" in chain
        assert "production_scheduling" in chain

    # ── 三智能体全链路 ──────────────────────────────────

    def test_three_agent_full_chain(self) -> None:
        data = self._post(
            "质量缺陷率上升，设备振动传感器报警，需要优化工艺参数来改善良品率"
        )
        assert data["execution_mode"] == "collaborative"
        assert len(data["agent_chain"]) == 3
        chain = [s["agent_name"] for s in data["agent_chain"]]
        assert "quality_inspection" in chain
        assert "predictive_maintenance" in chain
        assert "process_parameter_optimization" in chain

    # ── 协同结构完整性 ──────────────────────────────────

    def test_collaborative_has_complete_chain_details(self) -> None:
        data = self._post("排产前需要检查供应链库存是否充足，避免缺料影响交期")
        for step in data["agent_chain"]:
            assert step["agent_name"]
            assert step["display_name"]
            assert step["summary"]
            assert step["decision"]
            assert len(step["evidence"]) >= 1
            assert len(step["node_feedback"]) >= 3

    def test_collaborative_aggregates_node_feedback(self) -> None:
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")
        # 聚合节点数 >= 6（2 agents × 3 nodes each）
        assert len(data["node_feedback"]) >= 6

    def test_collaborative_has_composite_report(self) -> None:
        data = self._post(
            "质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率"
        )
        c = data["closure"]
        composite = [r for r in c["reports"] if "综合" in r["title"]]
        assert len(composite) >= 1

    def test_collaborative_has_composite_alert(self) -> None:
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")
        c = data["closure"]
        composite = [a for a in c["alerts"] if "协同" in a["title"]]
        assert len(composite) >= 1


# ══════════════════════════════════════════════════════════════════
# 端到端流水线：请求 → 路由 → 知识 → 推理 → 闭环 → 响应
# ══════════════════════════════════════════════════════════════════


class TestEndToEndPipeline:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def _post(self, text: str, agent_name: str | None = None) -> dict:
        body: dict = {"request_text": text, "require_llm": False}
        if agent_name:
            body["agent_name"] = agent_name
        resp = self.client.post(f"{API_PREFIX}/execute", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_e2e_single_agent_pipeline(self) -> None:
        """端到端：请求 → 路由 → 知识注入 → 推理 → 闭环 → 响应。"""
        data = self._post("分析供应链库存缺料风险")

        # 1. 路由
        assert data["agent_name"] == "supply_chain_management"
        # 2. 知识注入
        knowledge = [e for e in data["evidence"] if "[knowledge:" in e]
        assert len(knowledge) >= 1
        # 3. 推理输出
        assert data["summary"]
        assert data["decision"]
        # 4. 节点反馈
        assert len(data["node_feedback"]) >= 3
        # 5. 闭环
        c = data["closure"]
        assert len(c["reports"]) >= 1
        assert len(c["action_items"]) >= 1

    def test_e2e_collaborative_pipeline(self) -> None:
        """端到端协同：请求 → 多场景检测 → 知识注入 → 链式执行 → 聚合闭环。"""
        data = self._post("质量缺陷率上升，设备振动异常需要维护处理")

        # 1. 多场景检测
        assert data["execution_mode"] == "collaborative"
        assert len(data["detected_scenes"]) >= 2
        # 2. 执行链路
        assert len(data["agent_chain"]) == 2
        # 3. 知识注入在顶层和每个 step
        top_knowledge = [e for e in data["evidence"] if "[knowledge:" in e]
        assert len(top_knowledge) >= 1
        for step in data["agent_chain"]:
            step_knowledge = [e for e in step["evidence"] if "[knowledge:" in e]
            assert len(step_knowledge) >= 1
        # 4. 聚合输出
        assert data["summary"]
        assert data["decision"]
        assert len(data["node_feedback"]) >= 6
        # 5. 闭环
        c = data["closure"]
        assert len(c["reports"]) >= 3  # 2 per-agent + 1 composite

    def test_e2e_closed_loop_all_agents(self) -> None:
        """每个智能体单独走完整流水线。"""
        queries = {
            "production_scheduling": "优化排产计划提升产能",
            "quality_inspection": "分析质量缺陷根因",
            "predictive_maintenance": "设备振动需要维护",
            "supply_chain_management": "供应链库存缺料风险",
            "process_parameter_optimization": "优化工艺参数温度",
        }
        for agent_name, query in queries.items():
            data = self._post(query)
            # 基础字段
            assert data["trace_id"]
            assert data["agent_name"] == agent_name
            assert data["summary"]
            assert data["decision"]
            # 知识注入
            assert len(data["evidence"]) >= 1
            # 节点反馈
            assert len(data["node_feedback"]) >= 3
            # 闭环
            assert "closure" in data
            assert len(data["closure"]["reports"]) >= 1


# ══════════════════════════════════════════════════════════════════
# GET /agents/ 列表
# ══════════════════════════════════════════════════════════════════


class TestListAgents:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_list_agents_returns_five(self) -> None:
        resp = self.client.get(f"{API_PREFIX}/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        names = {a["name"] for a in data}
        for expected in AGENT_NAMES:
            assert expected in names, f"缺少: {expected}"

    def test_list_agents_returns_metadata(self) -> None:
        resp = self.client.get(f"{API_PREFIX}/")
        data = resp.json()
        for agent in data:
            assert "name" in agent
            assert "display_name" in agent
            assert "scenario_hint" in agent
            assert "input_schema" in agent
            assert "output_schema" in agent


# ══════════════════════════════════════════════════════════════════
# 案例沉淀验证 — 执行后可检索
# ══════════════════════════════════════════════════════════════════


class TestCasePrecipitation:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_execution_creates_retrievable_case(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        # 通过同一个 orchestrator 实例验证案例沉淀
        orch = AgentOrchestrator()
        count_before = orch.knowledge.case_count

        req = AgentTaskRequest(
            request_text="分析CNC设备振动传感器数据异常需要维护",
            require_llm=False,
        )
        import asyncio
        asyncio.run(orch.execute(req, db=None))

        # 执行后案例数应增加
        assert orch.knowledge.case_count > count_before
        # 搜索刚执行的案例
        results = orch.knowledge.search_cases("CNC设备振动传感器")
        assert len(results) >= 1


# ══════════════════════════════════════════════════════════════════
# 幂等性与一致性
# ══════════════════════════════════════════════════════════════════


class TestIdempotency:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_same_request_returns_consistent_agent(self) -> None:
        """相同请求应路由到相同智能体。"""
        for _ in range(3):
            resp = self.client.post(
                f"{API_PREFIX}/execute",
                json={"request_text": "分析质量缺陷和不良率原因", "require_llm": False},
            )
            assert resp.status_code == 200
            assert resp.json()["agent_name"] == "quality_inspection"

    def test_rapid_requests_dont_crash(self) -> None:
        """快速连续请求不应崩溃。"""
        for i in range(10):
            resp = self.client.post(
                f"{API_PREFIX}/execute",
                json={
                    "request_text": f"测试请求质量检测第{i}次",
                    "require_llm": False,
                },
            )
            assert resp.status_code == 200
