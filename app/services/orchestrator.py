"""增强主控 Orchestrator。

支持：
- 单智能体调用：根据请求文字路由到最匹配的智能体
- 多智能体协同调用：识别跨域场景，按序执行多个智能体
- 聚合节点反馈：接口层可见完整执行链路
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.registry import AgentRegistry
from app.core.config import get_settings
from app.core.logging import get_logger
from app.memory.memory_store import MemoryStore
from app.models.agent_run import AgentRun
from app.schemas.agent import (
    AgentStep,
    AgentTaskRequest,
    AgentTaskResponse,
    NodeFeedback,
    NodeStatus,
    OrchestrationResponse,
)
from app.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)

# ── 路由规则：关键词 → 智能体名称 ─────────────────────────

ROUTING_RULES: dict[str, list[str]] = {
    "production_scheduling": ["排产", "调度", "工单", "产能", "交期", "瓶颈"],
    "quality_inspection": ["质量", "缺陷", "不良", "质检", "良率", "根因"],
    "predictive_maintenance": ["设备", "故障", "停机", "维护", "振动", "传感器"],
    "supply_chain_management": ["供应链", "采购", "库存", "交付", "缺料", "BOM", "物料"],
    "process_parameter_optimization": ["工艺", "参数", "温度", "压力", "优化", "良品率"],
}

# ── 多智能体协同场景 ──────────────────────────────────────
# 当请求命中多个域的关键词时，按预定义链执行

COLLABORATIVE_CHAINS: dict[str, list[str]] = {
    # 质量 + 设备 → 先分析质量，再检查设备维护
    "quality_inspection+predictive_maintenance": [
        "quality_inspection",
        "predictive_maintenance",
    ],
    # 排产 + 供应链 → 先检查供应链物料，再优化排产
    "supply_chain_management+production_scheduling": [
        "supply_chain_management",
        "production_scheduling",
    ],
    # 质量 + 工艺 → 先分析质量缺陷，再优化工艺参数
    "quality_inspection+process_parameter_optimization": [
        "quality_inspection",
        "process_parameter_optimization",
    ],
    # 设备 + 排产 → 先评估设备状态，再调整排产
    "predictive_maintenance+production_scheduling": [
        "predictive_maintenance",
        "production_scheduling",
    ],
    # 质量 + 设备 + 工艺 → 全链路协同
    "quality_inspection+predictive_maintenance+process_parameter_optimization": [
        "quality_inspection",
        "predictive_maintenance",
        "process_parameter_optimization",
    ],
}

# 最少关键词命中数才会触发协同
MIN_COLLABORATIVE_SCENES = 2


class AgentOrchestrator:
    """增强主控 Orchestrator。

    使用方式:
        orchestrator = AgentOrchestrator()

        # 单智能体
        resp = await orchestrator.execute(AgentTaskRequest(request_text="分析质量缺陷"))

        # 多智能体协同（自动检测）
        resp = await orchestrator.execute(AgentTaskRequest(
            request_text="质量缺陷导致设备停机，需要同时优化工艺参数"
        ))
        # resp.execution_mode == "collaborative"
        # resp.agent_chain 包含 3 个 AgentStep
    """

    def __init__(self) -> None:
        self.registry = AgentRegistry()
        self.settings = get_settings()
        self.memory = MemoryStore(self.settings.memory_file)
        self.knowledge = KnowledgeService()

    # ── 场景识别 ──────────────────────────────────────────

    def detect_scenes(self, text: str) -> list[str]:
        """识别请求涉及的业务场景（可多个）。

        按关键词命中数排序，返回匹配的智能体名称列表。
        """
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for agent_name, keywords in ROUTING_RULES.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > 0:
                scores[agent_name] = hits

        # 按命中数降序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in ranked]

    def route_agent(self, request: AgentTaskRequest) -> str:
        """单智能体路由：返回最匹配的智能体名称。"""
        if request.agent_name:
            return request.agent_name

        scenes = self.detect_scenes(request.request_text)
        return scenes[0] if scenes else "production_scheduling"

    def resolve_chain(self, scenes: list[str]) -> list[str] | None:
        """解析多智能体协同链。

        如果检测到的场景 ≥ 2 且有预定义协同链，返回链；
        否则返回 None（走单智能体）。
        """
        if len(scenes) < MIN_COLLABORATIVE_SCENES:
            return None

        # 精确匹配预定义链
        key = "+".join(sorted(scenes))
        if key in COLLABORATIVE_CHAINS:
            return COLLABORATIVE_CHAINS[key]

        # 模糊匹配：尝试找到包含所有场景的最长链
        for chain_key, chain in COLLABORATIVE_CHAINS.items():
            chain_scenes = set(chain_key.split("+"))
            if set(scenes).issubset(chain_scenes):
                return chain

        return None

    # ── 知识检索辅助 ──────────────────────────────────────

    def _retrieve_knowledge_evidence(self, request_text: str) -> list[str]:
        """检索知识库并返回带来源标记的 evidence 行。"""
        results = self.knowledge.retrieve(request_text, limit=5)
        if not results:
            return []
        return [
            f"[knowledge:{r.source_name}] {r.snippet[:120]}"
            for r in results
        ]

    def _store_case(
        self,
        request_text: str,
        agent_name: str,
        decision: str,
        summary: str,
        evidence: list[str],
        next_actions: list[str],
        execution_mode: str,
    ) -> None:
        """将执行结果沉淀为知识案例。"""
        self.knowledge.add_case(
            request_text=request_text,
            agent_name=agent_name,
            decision=decision,
            summary=summary,
            evidence=evidence,
            next_actions=next_actions,
            execution_mode=execution_mode,
        )

    # ── 单智能体执行 ──────────────────────────────────────

    async def _execute_single(
        self,
        trace_id: str,
        request: AgentTaskRequest,
        agent_name: str,
        db: Session | None,
    ) -> AgentTaskResponse:
        """执行单个智能体并返回标准响应。"""
        agent = self.registry.get(agent_name)
        result = agent.plan(request.request_text, request.context)
        node_feedback = agent.build_node_feedback(request.request_text, result)

        # 知识检索注入 evidence
        knowledge_evidence = self._retrieve_knowledge_evidence(
            request.request_text
        )
        combined_evidence = [*result.evidence, *knowledge_evidence]

        self.memory.append(
            title=f"{agent.display_name} | {trace_id}",
            lines=[
                f"request: {request.request_text}",
                f"decision: {result.decision}",
                *[f"next: {item}" for item in result.next_actions],
            ],
        )

        if db is not None:
            try:
                db.add(
                    AgentRun(
                        trace_id=trace_id,
                        agent_name=agent_name,
                        request_text=request.request_text,
                        response_text=result.summary,
                    )
                )
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                logger.warning("agent run persistence skipped: %s", exc)

        # 案例沉淀
        self._store_case(
            request_text=request.request_text,
            agent_name=agent_name,
            decision=result.decision,
            summary=result.summary,
            evidence=combined_evidence,
            next_actions=result.next_actions,
            execution_mode="single",
        )

        return AgentTaskResponse(
            trace_id=trace_id,
            agent_name=agent_name,
            summary=result.summary,
            decision=result.decision,
            evidence=combined_evidence,
            next_actions=result.next_actions,
            node_feedback=node_feedback,
            memory_updated=True,
        )

    # ── 多智能体协同执行 ──────────────────────────────────

    async def _execute_collaborative(
        self,
        trace_id: str,
        request: AgentTaskRequest,
        chain: list[str],
        db: Session | None,
    ) -> OrchestrationResponse:
        """按协同链依次执行多个智能体，聚合输出。"""
        agent_steps: list[AgentStep] = []
        all_node_feedback: list[NodeFeedback] = []
        all_evidence: list[str] = []
        all_next_actions: list[str] = []
        summaries: list[str] = []
        decisions: list[str] = []

        # 知识检索（一次，所有 agent 共享）
        knowledge_evidence = self._retrieve_knowledge_evidence(
            request.request_text
        )

        # 上下文传递：前一个 agent 的产出注入下一个 agent 的 context
        accumulated_context: dict[str, str] = dict(request.context)

        for agent_name in chain:
            meta = self.registry.meta(agent_name)
            agent = self.registry.get(agent_name)

            # 构建带上下文的请求
            step_request = AgentTaskRequest(
                request_text=request.request_text,
                agent_name=agent_name,
                context=accumulated_context,
                require_llm=False,  # 协同链中不逐个调 LLM
            )

            result = agent.plan(step_request.request_text, step_request.context)
            nf = agent.build_node_feedback(step_request.request_text, result)

            # 标记节点归属
            for node in nf:
                node.node_id = f"{agent_name}/{node.node_id}"

            # 注入知识到每个 step 的 evidence
            step_evidence = [*result.evidence, *knowledge_evidence]

            step = AgentStep(
                agent_name=agent_name,
                display_name=meta.display_name,
                status="completed",
                summary=result.summary,
                decision=result.decision,
                evidence=step_evidence,
                next_actions=result.next_actions,
                node_feedback=nf,
            )
            agent_steps.append(step)
            all_node_feedback.extend(nf)
            all_evidence.extend(
                f"[{meta.display_name}] {e}" for e in result.evidence
            )
            all_evidence.extend(knowledge_evidence)
            all_next_actions.extend(result.next_actions)
            summaries.append(f"[{meta.display_name}] {result.summary}")
            decisions.append(result.decision)

            # 更新累积上下文供下游使用
            accumulated_context["previous_agent"] = agent_name
            accumulated_context["previous_decision"] = result.decision
            accumulated_context["previous_summary"] = result.summary

            # 持久化每个步骤
            if db is not None:
                try:
                    db.add(
                        AgentRun(
                            trace_id=f"{trace_id}/{agent_name}",
                            agent_name=agent_name,
                            request_text=request.request_text,
                            response_text=result.summary,
                        )
                    )
                except SQLAlchemyError as exc:
                    logger.warning("chain step persistence skipped: %s", exc)

        if db is not None:
            try:
                db.commit()
            except SQLAlchemyError:
                db.rollback()

        # 记忆
        self.memory.append(
            title=f"协同链 {' → '.join(chain)} | {trace_id}",
            lines=[
                f"request: {request.request_text}",
                f"scenes: {', '.join(chain)}",
                *[f"[{s.display_name}] {s.decision}" for s in agent_steps],
            ],
        )

        # 案例沉淀
        self._store_case(
            request_text=request.request_text,
            agent_name="+".join(chain),
            decision=self._synthesize_decision(decisions),
            summary=self._synthesize_summary(chain, summaries, decisions),
            evidence=all_evidence,
            next_actions=all_next_actions,
            execution_mode="collaborative",
        )

        # 聚合输出
        return OrchestrationResponse(
            trace_id=trace_id,
            request_text=request.request_text,
            detected_scenes=chain,
            execution_mode="collaborative",
            agent_name="+".join(chain),
            summary=self._synthesize_summary(chain, summaries, decisions),
            decision=self._synthesize_decision(decisions),
            evidence=all_evidence,
            next_actions=all_next_actions,
            agent_chain=agent_steps,
            node_feedback=all_node_feedback,
            memory_updated=True,
        )

    # ── 聚合逻辑 ──────────────────────────────────────────

    @staticmethod
    def _synthesize_summary(
        chain: list[str], summaries: list[str], decisions: list[str]
    ) -> str:
        """将多智能体摘要合成为统一摘要。"""
        parts = [f"协同分析完成（{' → '.join(chain)}）"]
        for i, (name, s) in enumerate(zip(chain, summaries)):
            parts.append(f"第{i+1}步-{name}：{s}")
        return "；".join(parts)

    @staticmethod
    def _synthesize_decision(decisions: list[str]) -> str:
        """合成多智能体联合决策。

        优先级：任一 agent 检测到风险 → 报告风险，否则取多数。
        """
        risk_keywords = ["risk", "critical", "shortage", "detected", "urgent"]
        for d in decisions:
            if any(kw in d for kw in risk_keywords):
                return f"协同决策-风险：{' | '.join(decisions)}"
        return f"协同决策：{' | '.join(decisions)}"

    # ── 统一入口 ──────────────────────────────────────────

    async def execute(
        self,
        request: AgentTaskRequest,
        db: Session | None = None,
    ) -> OrchestrationResponse:
        """统一执行入口 — 自动检测单/多智能体场景。

        返回 OrchestrationResponse，包含：
        - execution_mode: "single" 或 "collaborative"
        - agent_chain: 完整执行链路
        - node_feedback: 聚合所有智能体的节点反馈
        """
        trace_id = uuid4().hex

        # 显式指定 → 单智能体
        if request.agent_name:
            single_resp = await self._execute_single(
                trace_id, request, request.agent_name, db
            )
            return OrchestrationResponse(
                trace_id=trace_id,
                request_text=request.request_text,
                detected_scenes=[request.agent_name],
                execution_mode="single",
                agent_name=single_resp.agent_name,
                summary=single_resp.summary,
                decision=single_resp.decision,
                evidence=single_resp.evidence,
                next_actions=single_resp.next_actions,
                agent_chain=[
                    AgentStep(
                        agent_name=single_resp.agent_name,
                        display_name=self.registry.meta(
                            single_resp.agent_name
                        ).display_name,
                        summary=single_resp.summary,
                        decision=single_resp.decision,
                        evidence=single_resp.evidence,
                        next_actions=single_resp.next_actions,
                        node_feedback=single_resp.node_feedback,
                    )
                ],
                node_feedback=single_resp.node_feedback,
                memory_updated=single_resp.memory_updated,
            )

        # 自动场景检测
        scenes = self.detect_scenes(request.request_text)
        chain = self.resolve_chain(scenes)

        if chain is None or len(chain) <= 1:
            # 单智能体
            agent_name = scenes[0] if scenes else "production_scheduling"
            single_resp = await self._execute_single(
                trace_id, request, agent_name, db
            )
            meta = self.registry.meta(agent_name)
            return OrchestrationResponse(
                trace_id=trace_id,
                request_text=request.request_text,
                detected_scenes=scenes,
                execution_mode="single",
                agent_name=agent_name,
                summary=single_resp.summary,
                decision=single_resp.decision,
                evidence=single_resp.evidence,
                next_actions=single_resp.next_actions,
                agent_chain=[
                    AgentStep(
                        agent_name=agent_name,
                        display_name=meta.display_name,
                        summary=single_resp.summary,
                        decision=single_resp.decision,
                        evidence=single_resp.evidence,
                        next_actions=single_resp.next_actions,
                        node_feedback=single_resp.node_feedback,
                    )
                ],
                node_feedback=single_resp.node_feedback,
                memory_updated=single_resp.memory_updated,
            )

        # 多智能体协同
        return await self._execute_collaborative(trace_id, request, chain, db)
