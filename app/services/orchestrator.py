"""增强主控 Orchestrator。

支持：
- 单智能体调用：根据请求文字路由到最匹配的智能体
- 多智能体协同调用：识别跨域场景，按序执行多个智能体
- 聚合节点反馈：接口层可见完整执行链路
- 业务问答增强：委托 BusinessAnswerService 生成解释型答案
"""

from __future__ import annotations

from typing import Any
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
from app.services.business_answer_service import (
    BusinessAnswerService,
    _detect_knowledge_domains,
    _generate_local_knowledge_answer,
    _is_business_explanation_question,
    _matches_knowledge_question,
    validate_summary,
)
from app.services.deepseek_client import DeepSeekClient
from app.services.knowledge_service import KnowledgeService
from app.services.mcp_gateway import MCPGateway, MCPGatewayResult

logger = get_logger(__name__)

# ── 路由规则：关键词 → 智能体名称 ─────────────────────────

ROUTING_RULES: dict[str, list[str]] = {
    "production_scheduling": ["排产", "调度", "工单", "产能", "交期", "瓶颈"],
    "quality_inspection": [
        "质量", "缺陷", "不良", "质检", "良率", "根因",
        "不合格", "不达标", "超标", "零件", "检验", "检测",
    ],
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

    def __init__(
        self,
        llm_client: Any = None,
        mcp_gateway: MCPGateway | None = None,
    ) -> None:
        self.registry = AgentRegistry()
        self.settings = get_settings()
        self.memory = MemoryStore(self.settings.memory_file)
        self.knowledge = KnowledgeService()
        self._llm = llm_client if llm_client is not None else DeepSeekClient()
        self._mcp_gateway = (
            mcp_gateway if mcp_gateway is not None else MCPGateway(self.settings)
        )
        self._answer_service = BusinessAnswerService(
            llm_client=self._llm, registry=self.registry
        )

    async def _prepare_mcp_request(
        self,
        request: AgentTaskRequest,
    ) -> tuple[AgentTaskRequest, MCPGatewayResult]:
        mcp_result = await self._mcp_gateway.enrich_request(
            request.request_text,
            request.context,
        )
        if not mcp_result.context:
            return request, mcp_result

        merged_context = {**request.context, **mcp_result.context}
        return request.model_copy(update={"context": merged_context}), mcp_result

    @staticmethod
    def _append_mcp_result(
        response: OrchestrationResponse,
        mcp_result: MCPGatewayResult,
    ) -> None:
        if mcp_result.evidence:
            response.evidence.extend(mcp_result.evidence)
        if mcp_result.node_feedback:
            response.node_feedback.extend(mcp_result.node_feedback)

    # ── 知识型问题答案生成 ─────────────────────────────────

    async def _generate_knowledge_answer(
        self, request_text: str, agent_names: list[str],
        use_llm: bool = True,
    ) -> str | None:
        """当用户问题属于知识解释型时，生成真正的解释型答案。

        委托 BusinessAnswerService：
        当 use_llm=True 时优先调 LLM，失败后本地模板兜底；
        当 use_llm=False 时直接走本地模板，不访问 DeepSeekClient。
        只在本地模板也无法生成时才返回 None。
        """
        return await self._answer_service.generate_answer(
            request_text, agent_names, use_llm=use_llm
        )

    @staticmethod
    def _build_answer_synthesis_node(answer_len: int) -> NodeFeedback:
        """构建'答案综合'节点反馈，标记解释型答案已生成。"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return NodeFeedback(
            node_id="answer-synthesis",
            node_name="答案综合",
            status="completed",
            detail=f"已根据用户问题生成解释型技术方案（{answer_len}字）",
            started_at=now,
            completed_at=now,
        )

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
        synthesized_summary = self._synthesize_summary(
            chain, summaries, decisions, self.registry,
            all_evidence=all_evidence, all_next_actions=all_next_actions,
        )
        self._store_case(
            request_text=request.request_text,
            agent_name="+".join(chain),
            decision=self._synthesize_decision(decisions),
            summary=synthesized_summary,
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
            summary=synthesized_summary,
            decision=self._synthesize_decision(decisions),
            evidence=all_evidence,
            next_actions=all_next_actions,
            agent_chain=agent_steps,
            node_feedback=all_node_feedback,
            memory_updated=True,
        )

    # ── 聚合逻辑 ──────────────────────────────────────────

    # 智能体角色描述（用于合成报告）
    _AGENT_ROLES: dict[str, str] = {
        "production_scheduling": "分析排产约束、交期冲突和产能瓶颈",
        "quality_inspection": "检测缺陷模式、追溯根因、评估质量风险",
        "predictive_maintenance": "评估设备健康状态、预测故障趋势",
        "supply_chain_management": "核算物料供需缺口、评估采购与库存风险",
        "process_parameter_optimization": "分析参数-质量关系、推荐优化方向",
    }

    # 领域问题上下文映射
    _DOMAIN_CONTEXT: dict[str, str] = {
        "production_scheduling": "排产调度",
        "quality_inspection": "质量缺陷",
        "predictive_maintenance": "设备维护",
        "supply_chain_management": "供应链物料",
        "process_parameter_optimization": "工艺参数",
    }

    @classmethod
    def _synthesize_summary(
        cls,
        chain: list[str],
        summaries: list[str],
        decisions: list[str],
        registry=None,
        all_evidence: list[str] | None = None,
        all_next_actions: list[str] | None = None,
    ) -> str:
        """将多智能体输出合成为统一的结构化分析报告。"""
        # ── 显示名 ──
        def _display(name: str) -> str:
            if registry is not None:
                try:
                    return registry.meta(name).display_name
                except Exception:
                    pass
            name_cn: dict[str, str] = {
                "quality_inspection": "质量检测",
                "predictive_maintenance": "设备预测性维护",
                "process_parameter_optimization": "工艺参数优化",
                "production_scheduling": "生产调度",
                "supply_chain_management": "供应链管理",
            }
            return name_cn.get(name, name)

        evidence_list = all_evidence or []
        next_actions_list = all_next_actions or []

        # ── 过滤原始 RAG / memory 证据 ──
        valid_evidence = cls._filter_evidence(evidence_list, chain, _display)

        # ── 分类 next_actions：业务步骤 vs 数据需求 ──
        valid_actions, data_request_actions = cls._classify_actions(
            next_actions_list
        )

        # ── 有效 decisions ──
        valid_decisions = [
            d for i, d in enumerate(decisions)
            if d and "已接收" not in d and "data_insufficient" not in d
        ]

        lines: list[str] = []

        # ── 1. 问题判断 ──
        domains = [cls._DOMAIN_CONTEXT.get(name, _display(name)) for name in chain]
        lines.append("【问题判断】")
        lines.append(
            f"根据您的提问，系统识别到该问题涉及 {len(chain)} 个关联业务领域："
            f"{'、'.join(domains)}。"
            "这些问题之间存在因果关系或上下游依赖，需协同分析。"
        )
        lines.append("")

        # ── 2. 涉及智能体 ──
        lines.append("【涉及智能体】")
        for name in chain:
            lines.append(f"  - {_display(name)}：{cls._AGENT_ROLES.get(name, '分析相关业务')}")
        lines.append("")

        # ── 3. 核心分析 ──
        lines.append("【核心分析】")
        core_points = cls._build_core_analysis(chain, valid_evidence, valid_decisions)
        for pt in core_points:
            lines.append(f"  - {pt}")
        lines.append("")

        # ── 4. 方法步骤 ──
        lines.append("【方法步骤】")
        steps = cls._build_method_steps(chain, valid_actions)
        for i, step in enumerate(steps):
            lines.append(f"  {i + 1}. {step}")
        lines.append("")

        # ── 5. 落地建议 ──
        lines.append("【落地建议】")
        suggestions = cls._generate_domain_suggestions(chain)
        for s in suggestions[:6]:
            lines.append(f"  - {s}")
        lines.append("")

        # ── 6. 风险提醒 ──
        lines.append("【风险提醒】")
        risks = cls._extract_risks(chain, decisions, valid_evidence)
        for r in risks[:5]:
            lines.append(f"  - {r}")
        lines.append("")

        # ── 7. 后续需要的数据 ──
        lines.append("【后续需要的数据】")
        data_needs = cls._derive_data_needs(
            chain, valid_evidence, data_request_actions
        )
        for d in data_needs[:5]:
            lines.append(f"  - {d}")

        return "\n".join(lines)

    # ── 过滤与分类辅助 ────────────────────────────────────

    @classmethod
    def _filter_evidence(
        cls,
        evidence_list: list[str],
        chain: list[str],
        _display,
    ) -> list[str]:
        """过滤原始 RAG / memory / 文档标题等不可直接展示的证据。"""
        valid: list[str] = []
        for e in evidence_list:
            # 原始 knowledge 检索结果
            if "[knowledge:" in e:
                continue
            # 跨会话记忆
            if "跨会话记忆" in e:
                continue
            # 项目方案文档标题/片段
            if "项目方案" in e:
                continue
            # markdown 标题、trace、历史会话记录
            if any(m in e for m in [
                "trace", "会话记录", "历史记录", "memory:",
                "### ", "## ", "# ",
            ]):
                continue
            # 空洞 evidence
            if any(m in e for m in [
                "建议通过结构化接口", "请提供", "已接收请求",
                "输入校验失败", "数据为空",
            ]):
                continue
            # 去掉 agent 前缀
            clean = e
            for name in chain:
                dn = _display(name)
                clean = clean.replace(f"[{dn}] ", "").replace(f"[{name}] ", "")
            if clean.strip():
                valid.append(clean)
        # 去重
        seen: set[str] = set()
        unique: list[str] = []
        for e in valid:
            key = e[:60]
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return unique

    @classmethod
    def _classify_actions(
        cls, actions: list[str]
    ) -> tuple[list[str], list[str]]:
        """将 next_actions 分类为业务步骤和纯数据需求。

        Returns:
            (business_steps, data_requests): 业务步骤放【方法步骤】，
            数据需求放【后续需要的数据】。
        """
        data_request_markers = [
            "提供", "inspection_batch", "inspection_items",
            "defect_records", "equipment", "context",
            "historical_defects", "请传入", "请补充", "传入",
            "填写", "提交",
        ]
        business_steps: list[str] = []
        data_requests: list[str] = []

        for a in actions:
            if not a or not a.strip():
                continue
            if any(m in a for m in data_request_markers):
                data_requests.append(a)
            else:
                business_steps.append(a)

        return business_steps, data_requests

    # ── 核心分析构建 ──────────────────────────────────────

    @classmethod
    def _build_core_analysis(
        cls,
        chain: list[str],
        valid_evidence: list[str],
        valid_decisions: list[str],
    ) -> list[str]:
        """构建核心分析要点。

        优先使用过滤后的 evidence；不足时生成领域业务分析点。
        绝不展示原始 RAG / memory 片段。
        """
        points: list[str] = []

        if valid_evidence:
            points.extend(valid_evidence[:6])
            return points

        # ── evidence 不足 → 按领域生成业务分析点 ──
        analysis_generators: dict[str, list[str]] = {
            "quality_inspection": [
                "缺陷率上升需按缺陷类型（尺寸偏差/粗糙度/裂纹/气孔）、设备、"
                "班次、物料批次进行分层统计，识别缺陷集中点",
                "使用帕累托图定位 Top 3 缺陷类型，通常占 80% 以上不良",
                "对 Top 缺陷按人机料法环（4M1E）逐一排查："
                "操作人员变更/设备精度漂移/来料批次差异/工艺参数偏移/环境温湿度波动",
                "对比缺陷发生时间与设备异常/物料切换/人员换班时间窗口，锁定触发因素",
            ],
            "predictive_maintenance": [
                "振动异常需结合温度、电流、历史维修记录判断退化趋势："
                "振动 RMS 趋势持续上升通常指示磨损加剧",
                "对比振动频谱特征频率（BPFO/BPFI/齿轮啮合频率）判断具体故障模式",
                "关联缺陷发生时间与设备异常时间窗口："
                "设备状态恶化往往是质量缺陷的重要前兆",
            ],
            "supply_chain_management": [
                "根据生产计划展开 BOM 计算物料总需求，"
                "对比当前库存与在途采购评估物料缺口",
                "对关键物料（A 类）设置安全库存预警线，"
                "低于安全库存立即触发补货建议",
            ],
            "production_scheduling": [
                "统计各设备工时负荷率，识别负荷率 >85% 的瓶颈工序",
                "分析交期冲突订单：按优先级（客户等级/利润贡献）排序，"
                "评估产能缺口并制定加班/外协/拆批方案",
            ],
            "process_parameter_optimization": [
                "分析关键参数（温度/压力/速度/时间）与良品率的相关性，"
                "筛选显著影响因子",
                "参数漂移需追溯：设备老化导致的系统性偏移 vs 原材料批次波动导致的随机偏移",
            ],
        }

        for name in chain:
            gen = analysis_generators.get(name, [])
            for g in gen:
                if g not in points:
                    points.append(g)

        if valid_decisions and not points:
            points.append(
                f"综合判定：{'；'.join(valid_decisions[:3])}"
            )
        if not points:
            points.append("当前分析基于规则推理，建议结合实际运行数据进行深度分析")
        return points

    # ── 方法步骤构建 ──────────────────────────────────────

    @classmethod
    def _build_method_steps(
        cls, chain: list[str], business_actions: list[str]
    ) -> list[str]:
        """构建方法步骤 — 保证至少 5 条真正的业务处理步骤。

        不会展示"提供数据""传入参数"等字段收集内容。
        """
        steps: list[str] = []

        # 先用已有的业务 actions（去重）
        seen: set[str] = set()
        for a in business_actions:
            if a not in seen:
                seen.add(a)
                steps.append(a)
                if len(steps) >= 7:
                    break

        # 不足 5 条 → 按领域生成补充步骤
        if len(steps) < 5:
            domain_steps: dict[str, list[str]] = {
                "quality_inspection": [
                    "按产线/设备/班次/批次对缺陷率做分层统计，绘制 Pareto 图定位 Top 3 缺陷",
                    "对尺寸偏差、粗糙度等 Top 缺陷进行人机料法环逐项排查",
                    "对比缺陷发生时间与换班/换料/换型/设备报警时间窗口",
                    "对怀疑根因设计对照实验（单变量法），验证因果关系",
                ],
                "predictive_maintenance": [
                    "提取异常设备振动、温度、电流趋势数据，对信号做 FFT 频谱分析",
                    "建立设备健康基线（≥30天正常运行数据），计算 EWMA/CUSUM 控制限",
                    "关联缺陷发生时间与设备异常时间窗口，判断设备退化→质量缺陷的因果链",
                    "对关键设备制定维护窗口建议，避免与排产高峰冲突",
                ],
                "supply_chain_management": [
                    "按生产计划 × BOM 展开计算各物料总需求量和需求日期",
                    "对比当前可用库存 + 在途采购预计到货 vs 需求 + 安全库存",
                    "识别缺料风险物料并按风险等级分级：一般/严重/紧急",
                    "对缺料物料生成采购建议（数量/推荐供应商/最晚下单日）",
                ],
                "production_scheduling": [
                    "统计各设备/产线负荷率，识别瓶颈工序并计算产能缺口",
                    "按 EDD/CR 规则排序工单，瓶颈工序优先排产并建立时间缓冲",
                    "评估加班/外协/拆批/替代工艺等方案对交期满足率的影响",
                    "输出排产甘特图和延期风险工单清单",
                ],
                "process_parameter_optimization": [
                    "筛选显著影响良品率的关键工艺参数（相关性分析 + ANOVA 验证）",
                    "设计 DOE 实验方案（全因子/CCD/贝叶斯优化），确定最优参数区间",
                    "在最优参数下进行 3~5 次验证实验，确认良品率稳定性",
                    "将验证有效的参数写入 SOP 并锁定设备参数范围",
                ],
            }

            for name in chain:
                for s in domain_steps.get(name, []):
                    if s not in seen:
                        seen.add(s)
                        steps.append(s)
                        if len(steps) >= 7:
                            break
                if len(steps) >= 7:
                    break

        # 仍不足 → 补充协作步骤
        if len(steps) < 5:
            collaboration_fallbacks = [
                "汇总各维度分析结果，识别跨领域因果关系（如设备退化→质量缺陷→产能损失）",
                "按人机料法环输出根因假设列表并制定验证计划",
                "制定分阶段改善行动计划（紧急遏制→根本纠正→预防再发生）",
                "建立跨部门协同看板，跟踪各项改善措施的推进进度和KPI变化",
                "定期回顾改善效果，按PDCA循环持续优化",
            ]
            for s in collaboration_fallbacks:
                if s not in seen:
                    steps.append(s)
                    if len(steps) >= 5:
                        break

        return steps[:7]

    # ── 落地建议 ──────────────────────────────────────────

    @classmethod
    def _generate_domain_suggestions(cls, chain: list[str]) -> list[str]:
        """基于链中智能体生成领域专属的落地建议。"""
        suggestions: list[str] = []
        for name in chain:
            if name == "quality_inspection":
                suggestions.extend([
                    "建立质量数据看板，按产线/设备/班次实时监控缺陷率趋势",
                    "对 Top 3 缺陷开展 8D 专题攻关，每周跟踪改善进度",
                ])
            elif name == "predictive_maintenance":
                suggestions.extend([
                    "对关键设备部署振动/温度在线监测，建立健康基线（≥30天数据）",
                    "建立报警确认反馈闭环，运维人员确认结果回写系统优化阈值",
                ])
            elif name == "supply_chain_management":
                suggestions.extend([
                    "对 A 类物料设置安全库存并维持 ≥2 家合格供应商",
                    "推行月度 S&OP 会议，对齐销售预测、生产计划与采购计划",
                ])
            elif name == "production_scheduling":
                suggestions.extend([
                    "瓶颈设备建立产能缓冲（预留 10%~15% 产能应对插单）",
                    "每日晨会检视排产达成率，偏差 >10% 触发重排",
                ])
            elif name == "process_parameter_optimization":
                suggestions.extend([
                    "对关键工序实施 SPC 控制图监控，参数偏移时自动报警",
                    "将最优参数纳入 SOP 并锁定设备 HMI 参数范围防止误操作",
                ])
        suggestions.append("以上建议相互关联，建议组建跨部门小组协同推进")
        return suggestions

    # ── 风险提取 ──────────────────────────────────────────

    @classmethod
    def _extract_risks(
        cls, chain: list[str], decisions: list[str], evidence: list[str]
    ) -> list[str]:
        """从 decisions 和 evidence 中提取风险信号。"""
        risks: list[str] = []
        risk_keywords = [
            "risk", "critical", "shortage", "detected", "urgent",
            "风险", "严重", "缺料", "不足", "超标", "异常",
            "延迟", "偏高", "恶化",
        ]
        for d in decisions:
            if any(kw in d.lower() for kw in risk_keywords):
                # 去掉 "协同决策" 等前缀
                clean = d.replace("协同决策-风险：", "").replace("协同决策：", "")
                if clean and clean not in risks:
                    risks.append(clean)

        for e in evidence:
            if any(kw in e.lower() for kw in risk_keywords):
                clean = e[:120]
                # 去掉 agent 前缀
                for prefix_candidates in [
                    "[质量检测] ", "[设备预测性维护] ", "[工艺参数优化] ",
                    "[生产调度] ", "[供应链管理] ",
                ]:
                    clean = clean.replace(prefix_candidates, "")
                if clean and clean not in risks:
                    risks.append(clean)

        if not risks:
            risks.append("当前分析基于规则推理，建议获取实际运行数据后进行精确风险评估")
        return risks

    @classmethod
    def _derive_data_needs(
        cls,
        chain: list[str],
        evidence: list[str],
        data_request_actions: list[str],
    ) -> list[str]:
        """根据业务领域推导后续需要收集的数据。

        包含：
        - 领域预设的数据需求
        - 从 next_actions 分类出的数据请求（原"提供数据"类内容移到这里）
        """
        needs: list[str] = []
        for name in chain:
            if name == "quality_inspection":
                needs.append("最近 30 批次质检数据（含缺陷类型、数量、产线/设备/班次）")
            elif name == "predictive_maintenance":
                needs.append("关键设备近 90 天传感器数据（振动频谱、温度、电流）及历史维修记录")
            elif name == "supply_chain_management":
                needs.append("当前库存快照、在途采购单明细、BOM 表及未来 4 周生产计划")
            elif name == "production_scheduling":
                needs.append("待排产工单清单（含交期、工艺路线、标准工时）、设备可用产能日历")
            elif name == "process_parameter_optimization":
                needs.append("历史批次参数设定值与对应良品率数据（≥30 批）及参数允许范围")
        # 将分类出的数据请求放入此处（而非方法步骤）
        for a in data_request_actions:
            clean = a[:120]
            if clean not in needs:
                needs.append(clean)
        # 检查 evidence 中是否已有数据提示
        for e in evidence:
            if any(kw in e for kw in ["请提供", "需要", "缺少"]):
                clean = e[:120]
                if clean not in needs:
                    needs.append(clean)
        if not needs:
            needs.append("完整的生产运行数据（质检、设备、物料、工艺参数），以进行精确量化分析")
        return needs

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
        - node_feedback: 聚合所有智能体的节点反馈（含"答案综合"节点）

        知识解释型问题增强：
        - 检测到"如何/设计/方法"等问题时，优先调 LLM 生成答案
        - LLM 不可用（未配置/网络故障/API 错误）时回退到本地模板
        - 答案注入 summary，node_feedback 增加"答案综合"节点
        """
        trace_id = uuid4().hex
        request, mcp_result = await self._prepare_mcp_request(request)
        # 使用更宽松的业务解释型判断替代原有的知识关键词判断
        # _is_business_explanation_question 只要命中"解释型问法 + 业务领域"即触发
        is_knowledge = _is_business_explanation_question(
            request.request_text
        ) or _matches_knowledge_question(request.request_text)

        # ── 辅助函数：注入知识答案与答案综合节点 ──
        async def _inject_knowledge_answer(
            resp: OrchestrationResponse, agent_list: list[str]
        ) -> None:
            answer = await self._generate_knowledge_answer(
                request.request_text, agent_list,
                use_llm=request.require_llm,
            )
            if not answer:
                return
            # 验证答案质量：空洞回答不注入，避免覆盖智能体原始分析结果
            is_valid, violations = validate_summary(answer)
            if not is_valid:
                logger.warning(
                    "知识答案未通过质量验证，不注入 summary: %s",
                    "; ".join(violations),
                )
                return
            # 只覆盖顶层 summary，不覆盖 agent_chain 中各步骤的原始摘要。
            # 执行链路保留每个智能体的实际执行过程，顶部主答案展示知识答案。
            resp.summary = answer
            # 注入答案综合节点
            synthesis_node = self._build_answer_synthesis_node(len(answer))
            resp.node_feedback.append(synthesis_node)

        # ── 辅助函数：兜底质量门 ──
        # 对单智能体路径：如果 summary 仍为空洞流程话术
        #（如 "XX智能体已接收请求"），则调用 BusinessAnswerService
        # 生成业务分析模板兜底，确保独立智能体端点也有实质性答案。
        async def _ensure_quality_summary(
            resp: OrchestrationResponse, agent_list: list[str]
        ) -> None:
            current = resp.summary or ""

            # 快速判定：是否明显空洞
            hollow_markers = [
                "已接收请求", "建议通过结构化接口",
                "请提供完整", "传入完整",
            ]
            is_hollow = (
                any(m in current for m in hollow_markers)
                or len(current) < 120
            )
            if not is_hollow:
                # 再跑一遍 validate_summary 作为二次确认
                is_valid, _ = validate_summary(current)
                if is_valid:
                    return

            # 尝试用 BusinessAnswerService 生成兜底答案
            answer = await self._generate_knowledge_answer(
                request.request_text, agent_list,
                use_llm=request.require_llm,
            )
            if not answer:
                return

            is_valid2, violations2 = validate_summary(answer)
            if not is_valid2:
                logger.warning(
                    "兜底质量门生成的答案未通过验证: %s",
                    "; ".join(violations2),
                )
                return

            # 覆盖 summary，追加答案综合节点
            resp.summary = answer
            synthesis_node = self._build_answer_synthesis_node(len(answer))
            resp.node_feedback.append(synthesis_node)

        # 显式指定 → 单智能体
        if request.agent_name:
            single_resp = await self._execute_single(
                trace_id, request, request.agent_name, db
            )
            response = OrchestrationResponse(
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
            if is_knowledge:
                await _inject_knowledge_answer(response, [request.agent_name])
            await _ensure_quality_summary(response, [request.agent_name])
            self._append_mcp_result(response, mcp_result)
            return response

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
            response = OrchestrationResponse(
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
            if is_knowledge:
                await _inject_knowledge_answer(response, [agent_name])
            await _ensure_quality_summary(response, [agent_name])
            self._append_mcp_result(response, mcp_result)
            return response

        # 多智能体协同
        collab_response = await self._execute_collaborative(
            trace_id, request, chain, db
        )
        if is_knowledge:
            await _inject_knowledge_answer(collab_response, chain)
        await _ensure_quality_summary(collab_response, chain)
        self._append_mcp_result(collab_response, mcp_result)
        return collab_response
