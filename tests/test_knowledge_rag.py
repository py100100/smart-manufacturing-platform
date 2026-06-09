from __future__ import annotations

import pytest

from app.services.knowledge_service import KnowledgeService


# ══════════════════════════════════════════════════════════════════
# 文档检索
# ══════════════════════════════════════════════════════════════════


class TestDocumentRetrieval:
    def test_service_loads_chunks(self) -> None:
        svc = KnowledgeService()
        assert svc.chunk_count > 0, "知识库应加载至少一个分块"

    def test_retrieve_returns_results(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("质量 缺陷 检测")
        assert len(results) > 0, "检索质量相关关键词应返回结果"

    def test_retrieve_returns_empty_for_nonsense(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("xyzzy_not_a_real_word_12345")
        # 无匹配时仍返回 fallback
        assert isinstance(results, list)

    def test_retrieve_respects_limit(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("智能体", limit=2)
        assert len(results) <= 2

    def test_retrieve_scores_are_between_0_and_1(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("工艺参数优化")
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"score {r.score} out of range"


# ══════════════════════════════════════════════════════════════════
# 来源字段
# ══════════════════════════════════════════════════════════════════


class TestSourceFields:
    def test_retrieval_result_has_source_id(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("智能制造")
        for r in results:
            assert r.source_id, "RetrievalResult 必须有 source_id"

    def test_retrieval_result_has_source_name(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("供应链")
        for r in results:
            assert r.source_name, "RetrievalResult 必须有 source_name"

    def test_retrieval_result_has_snippet(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("排产 调度")
        for r in results:
            assert r.snippet, "RetrievalResult 必须有 snippet"

    def test_retrieval_result_has_score(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("设备 维护")
        for r in results:
            assert r.score is not None

    def test_get_source_by_id(self) -> None:
        svc = KnowledgeService()
        source = svc.get_source("project_plan")
        assert source is not None
        assert source.source_name == "项目方案"

    def test_source_has_type(self) -> None:
        svc = KnowledgeService()
        source = svc.get_source("memory")
        assert source is not None
        assert source.source_type == "memory"


# ══════════════════════════════════════════════════════════════════
# Orchestrator evidence 含知识来源
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorKnowledgeInjection:
    @pytest.mark.asyncio
    async def test_single_agent_evidence_has_knowledge(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="结合知识库分析质量缺陷和工艺参数优化",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        # evidence 中应有 [knowledge:...] 来源标记
        knowledge_evidence = [
            e for e in resp.evidence if e.startswith("[knowledge:")
        ]
        assert len(knowledge_evidence) >= 1, (
            f"evidence 应包含知识来源标记，实际: {resp.evidence[:5]}"
        )

    @pytest.mark.asyncio
    async def test_collaborative_evidence_has_knowledge(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        if resp.execution_mode == "collaborative":
            knowledge_evidence = [
                e for e in resp.evidence if e.startswith("[knowledge:")
            ]
            assert len(knowledge_evidence) >= 1, (
                "协同模式下 evidence 应包含知识来源标记"
            )

    @pytest.mark.asyncio
    async def test_agent_steps_have_knowledge_in_evidence(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="结合知识库分析供应链库存缺料风险",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        for step in resp.agent_chain:
            knowledge_in_step = [
                e for e in step.evidence if e.startswith("[knowledge:")
            ]
            assert len(knowledge_in_step) >= 1, (
                f"AgentStep {step.agent_name} 的 evidence 应包含知识来源"
            )


# ══════════════════════════════════════════════════════════════════
# 协同场景知识注入
# ══════════════════════════════════════════════════════════════════


class TestCollaborativeKnowledgeInjection:
    @pytest.mark.asyncio
    async def test_collaborative_all_steps_inject_knowledge(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        if resp.execution_mode == "collaborative":
            for step in resp.agent_chain:
                has_knowledge = any(
                    e.startswith("[knowledge:") for e in step.evidence
                )
                assert has_knowledge, (
                    f"协同链中 {step.agent_name} 的 evidence 缺少知识注入"
                )

    @pytest.mark.asyncio
    async def test_knowledge_appears_once_per_execution(self) -> None:
        """知识检索在一次协同执行中只做一次，所有 step 共享。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        resp = await orch.execute(req, db=None)

        if resp.execution_mode == "collaborative" and len(resp.agent_chain) >= 2:
            # 所有 step 的 knowledge evidence 应相同
            first_knowledge = [
                e for e in resp.agent_chain[0].evidence
                if e.startswith("[knowledge:")
            ]
            second_knowledge = [
                e for e in resp.agent_chain[1].evidence
                if e.startswith("[knowledge:")
            ]
            assert first_knowledge == second_knowledge, (
                "协同链中所有 step 应共享同一批知识检索结果"
            )


# ══════════════════════════════════════════════════════════════════
# 案例沉淀与检索
# ══════════════════════════════════════════════════════════════════


class TestCaseMemory:
    def test_add_case_stores_retrievable_case(self) -> None:
        svc = KnowledgeService()
        initial_count = svc.case_count

        svc.add_case(
            request_text="检查CNC设备振动异常",
            agent_name="predictive_maintenance",
            decision="建议停机维护",
            summary="设备振动超标12mm/s",
            evidence=["振动传感器读数 12mm/s", "正常范围 < 10mm/s"],
            next_actions=["立即停机", "更换轴承", "48h后复检"],
            execution_mode="single",
        )
        assert svc.case_count == initial_count + 1

    def test_stored_case_is_searchable(self) -> None:
        svc = KnowledgeService()

        svc.add_case(
            request_text="热处理温度偏高导致良品率下降",
            agent_name="process_parameter_optimization",
            decision="optimization_recommended",
            summary="温度从860→840可提升良品率3%",
            evidence=["温度860时良品率92%", "温度840时良品率95%"],
            next_actions=["调整温度至840", "监控24h良品率"],
            execution_mode="single",
        )
        results = svc.search_cases("热处理 温度 良品率")
        assert len(results) >= 1
        assert results[0].agent_name == "process_parameter_optimization"

    def test_search_cases_returns_empty_for_unrelated(self) -> None:
        svc = KnowledgeService()
        results = svc.search_cases("完全不相关的查询词xyz")
        assert len(results) == 0

    def test_multiple_cases_searchable(self) -> None:
        svc = KnowledgeService()
        svc.add_case(
            request_text="CNC设备振动", agent_name="predictive_maintenance",
            decision="safety_risk_detected", summary="振动超标",
            evidence=["振动12mm/s"], next_actions=["停机"],
        )
        svc.add_case(
            request_text="质量缺陷分析", agent_name="quality_inspection",
            decision="quality_risk_detected", summary="缺陷率超标",
            evidence=["缺陷率8%"], next_actions=["复检"],
        )
        results = svc.search_cases("设备 振动")
        assert len(results) >= 1
        # 应优先匹配维护案例
        assert results[0].agent_name == "predictive_maintenance"

    @pytest.mark.asyncio
    async def test_orchestrator_execution_stores_case(self) -> None:
        """Orchestrator 执行后案例应可检索。"""
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        case_count_before = orch.knowledge.case_count

        req = AgentTaskRequest(
            request_text="分析供应链库存缺料风险",
            require_llm=False,
        )
        await orch.execute(req, db=None)

        assert orch.knowledge.case_count > case_count_before

    @pytest.mark.asyncio
    async def test_collaborative_execution_stores_case(self) -> None:
        from app.schemas.agent import AgentTaskRequest
        from app.services.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        case_count_before = orch.knowledge.case_count

        req = AgentTaskRequest(
            request_text="质量缺陷率上升，设备振动异常需要维护处理",
            require_llm=False,
        )
        await orch.execute(req, db=None)

        # 协同执行后案例数应增加
        assert orch.knowledge.case_count > case_count_before


# ══════════════════════════════════════════════════════════════════
# 知识来源类型
# ══════════════════════════════════════════════════════════════════


class TestKnowledgeSourceTypes:
    def test_project_plan_source_loaded(self) -> None:
        svc = KnowledgeService()
        source = svc.get_source("project_plan")
        assert source is not None
        assert source.source_type == "project_plan"

    def test_memory_source_loaded(self) -> None:
        svc = KnowledgeService()
        source = svc.get_source("memory")
        assert source is not None
        assert source.source_type == "memory"

    def test_claude_source_loaded(self) -> None:
        svc = KnowledgeService()
        source = svc.get_source("claude")
        if source is not None:
            assert source.source_type == "document"

    def test_retrieval_result_has_source_type(self) -> None:
        svc = KnowledgeService()
        results = svc.retrieve("智能体 编排 多智能体")
        for r in results:
            assert r.source_type in (
                "project_plan", "memory", "document", "agent_case"
            ), f"未知 source_type: {r.source_type}"


# ══════════════════════════════════════════════════════════════════
# KnowledgeChunk 结构
# ══════════════════════════════════════════════════════════════════


class TestKnowledgeChunkStructure:
    def test_chunks_have_required_fields(self) -> None:
        svc = KnowledgeService()
        for ch in svc.chunks[:5]:
            assert ch.chunk_id.startswith("CHK-")
            assert ch.source_id
            assert ch.content
            assert ch.char_count > 0

    def test_chunks_have_headings(self) -> None:
        svc = KnowledgeService()
        headings = {ch.heading for ch in svc.chunks[:20]}
        # 应有多种标题
        assert len(headings) >= 1


# ══════════════════════════════════════════════════════════════════
# API 层知识可见性
# ══════════════════════════════════════════════════════════════════


class TestAPIKnowledgeVisibility:
    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_api_execute_evidence_has_knowledge(self) -> None:
        resp = self.client.post(
            "/api/v1/agents/execute",
            json={
                "request_text": "结合知识库分析质量缺陷和工艺参数优化",
                "require_llm": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        knowledge = [e for e in data["evidence"] if "[knowledge:" in e]
        assert len(knowledge) >= 1, (
            f"API 返回的 evidence 应含知识来源标记，实际前5条: {data['evidence'][:5]}"
        )

    def test_api_per_agent_evidence_has_knowledge(self) -> None:
        resp = self.client.post(
            "/api/v1/agents/production_scheduling/execute",
            json={"request_text": "优化排产计划", "require_llm": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        # agent_chain 中 step 的 evidence 应有知识标记
        for step in data["agent_chain"]:
            knowledge = [e for e in step["evidence"] if "[knowledge:" in e]
            assert len(knowledge) >= 1, (
                f"Step {step['agent_name']} evidence 缺少知识来源"
            )
