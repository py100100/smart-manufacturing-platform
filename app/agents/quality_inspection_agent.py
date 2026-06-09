from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentResult, BaseAgent
from app.schemas.agent import NodeFeedback
from app.schemas.quality_inspection import (
    AgentDecision,
    DefectClassificationResult,
    DefectPatternInfo,
    QualityInspectionAgentOutput,
    QualityInspectionRequest,
    QualityNodeFeedback,
    RootCauseResult,
)
from app.services.quality_inspection_service import QualityInspectionService

# ── 任务书规定的强制节点名 ──────────────────────────────────────

REQUIRED_NODES = [
    "input_validation",
    "standard_matching",
    "metric_evaluation",
    "defect_classification",
    "pattern_detection",
    "root_cause_analysis",
    "recommendation_generation",
]


class QualityInspectionAgent(BaseAgent):
    """质量检测与缺陷分析智能体。

    职责：编排质量检测分析流程，调用 service 完成：
    - 输入校验 (input_validation)
    - 标准匹配 (standard_matching)
    - 指标评价 (metric_evaluation)
    - 缺陷分类 (defect_classification)
    - 模式识别 (pattern_detection)
    - 人机料法环根因追溯 (root_cause_analysis)
    - 改进建议生成 (recommendation_generation)

    输出标准化 AgentResult 与节点式反馈。
    不直接访问数据库、不直接调用模型客户端。
    """

    name = "quality_inspection"
    display_name = "质量检测与缺陷分析"
    scenario_hint = "质量、质检、缺陷、不良、良率、根因、指标"

    def __init__(self) -> None:
        self.service = QualityInspectionService()

    # ── 主入口 ────────────────────────────────────────────────

    def execute(
        self, request: QualityInspectionRequest
    ) -> QualityInspectionAgentOutput:
        """执行质量检测与缺陷分析全流程。"""
        nodes: list[QualityNodeFeedback] = []

        # 1. 输入校验
        if not self._validate_input(request, nodes):
            return self._build_error_output(nodes)

        # 2. 标准匹配
        standard_map = self._match_standards(request, nodes)

        # 3. 指标评价
        indicator_results = self._evaluate_metrics(request, nodes)

        # 4. 缺陷分类
        classification = self._classify_defects(request, nodes)

        # 5. 模式识别
        pattern_info = self._detect_patterns(request, classification, nodes)

        # 6. 根因追溯
        root_cause_result = self._trace_root_cause(request, classification, nodes)

        # 7. 建议生成
        recommendations = self._generate_recommendations(
            indicator_results, classification, pattern_info, root_cause_result, nodes
        )

        # 8. 推导决策并汇总输出
        return self._build_output(
            request, indicator_results, classification, pattern_info,
            root_cause_result, recommendations, nodes,
        )

    # ── 步骤 1：输入校验 ─────────────────────────────────────

    @staticmethod
    def _validate_input(
        request: QualityInspectionRequest, nodes: list[QualityNodeFeedback]
    ) -> bool:
        issues: list[str] = []

        if not request.inspection_batch:
            issues.append("质检批次信息缺失")
        if not request.inspection_items and not request.defect_records:
            issues.append("质检指标列表和缺陷记录均为空，至少提供一个")

        if issues:
            nodes.append(
                QualityNodeFeedback(
                    node="input_validation",
                    status="failed",
                    message="输入校验失败：" + "；".join(issues),
                )
            )
            return False

        context_info = ""
        if request.context:
            ctx = request.context
            ctx_parts: list[str] = []
            if ctx.operator_id:
                ctx_parts.append(f"操作者={ctx.operator_id}")
            if ctx.machine_id:
                ctx_parts.append(f"设备={ctx.machine_id}")
            if ctx.material_batch_id:
                ctx_parts.append(f"材料批次={ctx.material_batch_id}")
            if ctx.environment:
                ctx_parts.append(f"环境参数={ctx.environment}")
            if ctx.process_params:
                ctx_parts.append(f"工艺参数={ctx.process_params}")
            if ctx_parts:
                context_info = "；现场上下文: " + "，".join(ctx_parts)

        nodes.append(
            QualityNodeFeedback(
                node="input_validation",
                status="success",
                message=(
                    f"输入校验通过：批次 {request.inspection_batch.batch_id}，"
                    f"产品 {request.inspection_batch.product_id}，"
                    f"工序 {request.inspection_batch.process_step}，"
                    f"检验项 {len(request.inspection_items)} 项，"
                    f"缺陷记录 {len(request.defect_records)} 条，"
                    f"质量标准 {len(request.quality_standards)} 条，"
                    f"历史缺陷 {len(request.historical_defects)} 条"
                    + context_info
                ),
            )
        )
        return True

    # ── 步骤 2：标准匹配 ─────────────────────────────────────

    @staticmethod
    def _match_standards(
        request: QualityInspectionRequest, nodes: list[QualityNodeFeedback]
    ) -> dict[str, bool]:
        """为每个检验项匹配质量标准，输出匹配情况。"""
        service = QualityInspectionService()

        if not request.inspection_items:
            nodes.append(
                QualityNodeFeedback(
                    node="standard_matching",
                    status="success",
                    message="无检验指标项，跳过标准匹配。",
                )
            )
            return {}

        matched_count = 0
        missing_count = 0
        has_builtin = 0
        product_id = request.inspection_batch.product_id

        for item in request.inspection_items:
            # 尝试 quality_standards 匹配
            std = service.match_quality_standard(
                product_id, item.metric_name, request.quality_standards
            )
            if std is not None:
                matched_count += 1
            elif item.standard_min is not None or item.standard_max is not None:
                has_builtin += 1
            else:
                missing_count += 1

        detail_parts: list[str] = [
            f"共 {len(request.inspection_items)} 项指标："
            f"匹配到质量标准 {matched_count} 项，"
            f"使用自带上下限 {has_builtin} 项"
        ]
        status: str = "success"
        if missing_count > 0:
            detail_parts.append(f"，缺少标准 {missing_count} 项")
            status = "warning"

        nodes.append(
            QualityNodeFeedback(
                node="standard_matching",
                status=status,
                message="；".join(detail_parts),
            )
        )
        return {}

    # ── 步骤 3：指标评价 ─────────────────────────────────────

    @staticmethod
    def _evaluate_metrics(
        request: QualityInspectionRequest, nodes: list[QualityNodeFeedback]
    ) -> list:
        service = QualityInspectionService()

        if not request.inspection_items:
            nodes.append(
                QualityNodeFeedback(
                    node="metric_evaluation",
                    status="success",
                    message="无检验指标项，跳过指标评价。",
                )
            )
            return []

        results = service.judge_all_indicators(
            items=request.inspection_items,
            product_id=request.inspection_batch.product_id,
            quality_standards=request.quality_standards,
        )

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        standard_missing_count = sum(1 for r in results if r.standard_source == "none")

        status: str = "success"
        detail_parts: list[str] = [
            f"已评价 {len(results)} 项指标：合格 {passed_count}，不合格 {failed_count}"
        ]
        if standard_missing_count > 0:
            detail_parts.append(f"（其中 {standard_missing_count} 项缺少质量标准）")
            if failed_count > 0:
                status = "warning"

        nodes.append(
            QualityNodeFeedback(
                node="metric_evaluation",
                status="success" if failed_count == 0 else status,
                message="；".join(detail_parts),
            )
        )
        return results

    # ── 步骤 4：缺陷分类 ─────────────────────────────────────

    @staticmethod
    def _classify_defects(
        request: QualityInspectionRequest, nodes: list[QualityNodeFeedback]
    ) -> DefectClassificationResult:
        service = QualityInspectionService()

        if not request.defect_records:
            empty = DefectClassificationResult()
            nodes.append(
                QualityNodeFeedback(
                    node="defect_classification",
                    status="success",
                    message="无缺陷记录，跳过缺陷分类。",
                )
            )
            return empty

        classification = service.classify_defects(request.defect_records)

        sev_detail = "、".join(
            f"{sev}: {cnt}" for sev, cnt in classification.by_severity.items()
        )
        type_detail = (
            f"最高频缺陷类型: {classification.top_defect_type}"
            if classification.top_defect_type
            else "无缺陷类型记录"
        )

        has_critical = len(classification.critical_items) > 0
        nodes.append(
            QualityNodeFeedback(
                node="defect_classification",
                status="warning" if has_critical else "success",
                message=(
                    f"缺陷分类完成：总数 {classification.total_defects}，"
                    f"严重度分布 [{sev_detail}]；{type_detail}"
                ),
            )
        )
        return classification

    # ── 步骤 5：模式识别 ─────────────────────────────────────

    @staticmethod
    def _detect_patterns(
        request: QualityInspectionRequest,
        classification: DefectClassificationResult,
        nodes: list[QualityNodeFeedback],
    ) -> DefectPatternInfo:
        service = QualityInspectionService()

        if classification.total_defects == 0:
            empty = DefectPatternInfo()
            nodes.append(
                QualityNodeFeedback(
                    node="pattern_detection",
                    status="success",
                    message="无缺陷数据，跳过模式识别。",
                )
            )
            return empty

        pattern = service.detect_patterns(
            classification=classification,
            defect_records=request.defect_records,
            threshold=request.pattern_threshold,
        )

        nodes.append(
            QualityNodeFeedback(
                node="pattern_detection",
                status="warning" if pattern.pattern_detected else "success",
                message=(
                    "模式识别完成："
                    f"{'检测到缺陷模式' if pattern.pattern_detected else '未检测到显著模式'}；"
                    f"{pattern.detail}"
                ),
            )
        )
        return pattern

    # ── 步骤 6：根因追溯 ─────────────────────────────────────

    @staticmethod
    def _trace_root_cause(
        request: QualityInspectionRequest,
        classification: DefectClassificationResult,
        nodes: list[QualityNodeFeedback],
    ) -> RootCauseResult | None:
        service = QualityInspectionService()

        if classification.total_defects == 0 or not classification.top_defect_type:
            nodes.append(
                QualityNodeFeedback(
                    node="root_cause_analysis",
                    status="success",
                    message="无缺陷数据，跳过根因分析。",
                )
            )
            return None

        # 汇总环境数据：context.environment + 旧 environment_data
        env_data = dict(request.environment_data)
        if request.context and request.context.environment:
            env_data.update(request.context.environment)

        root_cause = service.trace_root_cause(
            defect_type=classification.top_defect_type,
            product_id=request.inspection_batch.product_id,
            process_step=request.inspection_batch.process_step,
            historical_defects=request.historical_defects,
            environment_data=env_data,
            context=request.context,
        )

        match_label = {
            "historical": "历史匹配",
            "rule_based": "规则推断",
            "none": "未匹配",
        }.get(root_cause.match_source, root_cause.match_source)

        nodes.append(
            QualityNodeFeedback(
                node="root_cause_analysis",
                status=(
                    "success"
                    if root_cause.root_cause_category != "unknown"
                    else "warning"
                ),
                message=(
                    f"根因追溯完成（{match_label}）："
                    f"类别={root_cause.root_cause_category}，"
                    f"置信度={root_cause.confidence:.0%}；"
                    f"{root_cause.root_cause[:100]}"
                ),
            )
        )
        return root_cause

    # ── 步骤 7：建议生成 ─────────────────────────────────────

    @staticmethod
    def _generate_recommendations(
        indicator_results: list,
        classification: DefectClassificationResult,
        pattern_info: DefectPatternInfo,
        root_cause_result: RootCauseResult | None,
        nodes: list[QualityNodeFeedback],
    ) -> list:
        service = QualityInspectionService()

        failed_indicators = [r for r in indicator_results if not r.passed]
        rc = root_cause_result or RootCauseResult()

        recommendations = service.generate_recommendations(
            classification=classification,
            pattern=pattern_info,
            root_cause=rc,
            failed_indicators=failed_indicators,
        )

        nodes.append(
            QualityNodeFeedback(
                node="recommendation_generation",
                status="success",
                message=f"生成 {len(recommendations)} 条改进建议",
            )
        )
        return recommendations

    # ── 输出构建 ──────────────────────────────────────────────

    @staticmethod
    def _build_output(
        request: QualityInspectionRequest,
        indicator_results: list,
        classification: DefectClassificationResult,
        pattern_info: DefectPatternInfo,
        root_cause_result: RootCauseResult | None,
        recommendations: list,
        nodes: list[QualityNodeFeedback],
    ) -> QualityInspectionAgentOutput:
        """汇总所有分析结果，推导决策并构建输出。"""
        rc = root_cause_result

        decision = QualityInspectionAgent._derive_decision(
            indicator_results, classification, pattern_info, rc
        )

        summary = QualityInspectionAgent._build_summary(
            request, indicator_results, classification, pattern_info, rc, decision
        )

        evidence = QualityInspectionAgent._build_evidence(
            request, indicator_results, classification, pattern_info, rc
        )

        next_actions = QualityInspectionAgent._build_next_actions(
            decision, classification, pattern_info, rc, recommendations
        )

        return QualityInspectionAgentOutput(
            summary=summary,
            decision=decision,
            evidence=evidence,
            next_actions=next_actions,
            node_feedback=nodes,
            indicator_results=indicator_results,
            classification=classification,
            pattern_info=pattern_info,
            root_cause_result=rc,
            recommendations=recommendations,
        )

    # ── 决策推导 ──────────────────────────────────────────────

    @staticmethod
    def _derive_decision(
        indicator_results: list,
        classification: DefectClassificationResult | None,
        pattern_info: DefectPatternInfo | None,
        root_cause_result: RootCauseResult | None,
    ) -> AgentDecision:
        """根据分析结果推导智能体决策。

        优先级（修正版）：
        critical_quality_issue 必须 > 一切 — 安全第一
        > pattern > historical_root_cause
        > quality_risk > standard_missing > passed
        """
        # 1. critical_quality_issue: 存在 critical 缺陷（最高优先级，不可被任何条件覆盖）
        if classification and classification.critical_items:
            return "critical_quality_issue"

        # 2. standard_missing: 所有不合格指标都因缺少标准
        if indicator_results:
            has_standard_missing = any(
                r.standard_source == "none" for r in indicator_results
            )
            if has_standard_missing:
                all_failed_are_missing = all(
                    r.standard_source == "none"
                    for r in indicator_results
                    if not r.passed
                )
                if all_failed_are_missing:
                    return "standard_missing"

        # 3. defect_pattern_detected: 缺陷模式已识别
        if pattern_info and pattern_info.pattern_detected:
            return "defect_pattern_detected"

        # 4. root_cause_identified: 仅历史匹配才算
        if (
            root_cause_result
            and root_cause_result.root_cause_category != "unknown"
            and root_cause_result.match_source == "historical"
        ):
            return "root_cause_identified"

        # 5. quality_risk_detected: 有不合格指标或缺陷
        if indicator_results:
            if any(not r.passed for r in indicator_results):
                return "quality_risk_detected"
        if classification and classification.total_defects > 0:
            return "quality_risk_detected"

        # 6. quality_passed: 全部通过
        return "quality_passed"

    # ── 摘要构建 ──────────────────────────────────────────────

    @staticmethod
    def _build_summary(
        request: QualityInspectionRequest,
        indicator_results: list,
        classification: DefectClassificationResult | None,
        pattern_info: DefectPatternInfo | None,
        root_cause_result: RootCauseResult | None,
        decision: AgentDecision,
    ) -> str:
        batch = request.inspection_batch
        base = (
            f"批次 {batch.batch_id}（产品 {batch.product_id}，"
            f"工序 {batch.process_step}）质量分析完成。"
        )

        decisions_cn: dict[AgentDecision, str] = {
            "quality_passed": "所有指标合格，无缺陷记录，质量通过。",
            "quality_risk_detected": "检测到质量风险，存在不合格指标或缺陷记录。",
            "defect_pattern_detected": "检测到缺陷聚集模式，需重点关注高频缺陷类型。",
            "critical_quality_issue": "存在严重（Critical）缺陷，需立即启动质量异常处理流程。",
            "root_cause_identified": "已识别缺陷根因，可依据分析结果采取纠正措施。",
            "standard_missing": "部分指标缺少质量标准定义，无法完成完整质量判定。",
        }

        detail = decisions_cn.get(decision, "")
        parts: list[str] = [base, detail]

        if indicator_results:
            failed = sum(1 for r in indicator_results if not r.passed)
            if failed > 0:
                parts.append(f"不合格指标 {failed}/{len(indicator_results)} 项。")

        if classification and classification.total_defects > 0:
            parts.append(
                f"缺陷总数 {classification.total_defects}，"
                f"最高频类型 '{classification.top_defect_type}'。"
            )

        if pattern_info and pattern_info.pattern_detected:
            parts.append(f"模式类型: {pattern_info.pattern_type}。")

        if root_cause_result and root_cause_result.root_cause_category != "unknown":
            parts.append(f"根因类别: {root_cause_result.root_cause_category}。")

        return " ".join(parts)

    # ── 证据构建 ──────────────────────────────────────────────

    @staticmethod
    def _build_evidence(
        request: QualityInspectionRequest,
        indicator_results: list,
        classification: DefectClassificationResult | None,
        pattern_info: DefectPatternInfo | None,
        root_cause_result: RootCauseResult | None,
    ) -> list[str]:
        evidence: list[str] = []

        evidence.append(
            f"质检批次 {request.inspection_batch.batch_id}，"
            f"产品 {request.inspection_batch.product_id}，"
            f"工序 {request.inspection_batch.process_step}"
        )

        # 上下文证据
        if request.context:
            ctx = request.context
            if ctx.operator_id:
                evidence.append(f"操作者: {ctx.operator_id}")
            if ctx.machine_id:
                evidence.append(f"设备: {ctx.machine_id}")
            if ctx.material_batch_id:
                evidence.append(f"材料批次: {ctx.material_batch_id}")

        if indicator_results:
            passed = sum(1 for r in indicator_results if r.passed)
            failed = [r for r in indicator_results if not r.passed]
            evidence.append(f"指标评价：合格 {passed}/{len(indicator_results)} 项")
            for f in failed[:5]:
                evidence.append(f"不合格项 [{f.metric_name}]: {f.note}")

        if classification and classification.total_defects > 0:
            evidence.append(
                f"缺陷分类：总数 {classification.total_defects}，"
                f"Critical {len(classification.critical_items)} 项"
            )
            for dt, count in sorted(
                classification.by_type.items(), key=lambda x: -x[1]
            )[:3]:
                evidence.append(f"缺陷类型 '{dt}': {count} 次")

        if pattern_info and pattern_info.pattern_detected:
            evidence.append(f"缺陷模式: {pattern_info.detail}")

        if root_cause_result and root_cause_result.root_cause_category != "unknown":
            evidence.append(
                f"根因追溯: {root_cause_result.root_cause_category} "
                f"(置信度 {root_cause_result.confidence:.0%})"
            )
            evidence.extend(root_cause_result.matched_evidence[:3])

        return evidence

    # ── 后续行动构建 ──────────────────────────────────────────

    @staticmethod
    def _build_next_actions(
        decision: AgentDecision,
        classification: DefectClassificationResult | None,
        pattern_info: DefectPatternInfo | None,
        root_cause_result: RootCauseResult | None,
        recommendations: list,
    ) -> list[str]:
        actions: list[str] = []

        if decision == "critical_quality_issue":
            actions.append("立即启动质量异常处理流程，隔离受影响批次。")
            if classification:
                actions.append(
                    f"对 {len(classification.critical_items)} 个 Critical 缺陷"
                    "逐项制定紧急纠正措施。"
                )

        if decision == "defect_pattern_detected":
            if pattern_info and pattern_info.high_frequency_types:
                for ft in pattern_info.high_frequency_types[:3]:
                    actions.append(f"针对高频缺陷 '{ft}' 成立专项改进小组。")
            actions.append("对缺陷集中工序开展过程能力（CPK）分析。")

        if decision == "quality_risk_detected":
            if classification and classification.total_defects > 0:
                actions.append("对不合格项进行复查，确认测量系统（MSA）有效性。")
            actions.append("加强该工序的过程巡检频次。")

        if decision == "root_cause_identified" and root_cause_result:
            actions.append(
                f"执行根因纠正措施: {root_cause_result.corrective_action[:120]}"
            )
            actions.append("设定验证周期，跟踪纠正措施有效性。")

        if decision == "standard_missing":
            actions.append("为缺失质量标准的指标补充标准定义。")
            actions.append("在标准补全前，使用 inspection_items 自带上下限进行临时判定。")

        if decision == "quality_passed":
            actions.append("按计划执行下一批次质检。")
            actions.append("持续监控过程能力指标。")

        for rec in recommendations[:3]:
            if rec.action not in actions:
                actions.append(rec.action[:150])

        return actions

    # ── 错误输出 ──────────────────────────────────────────────

    @staticmethod
    def _build_error_output(
        nodes: list[QualityNodeFeedback],
    ) -> QualityInspectionAgentOutput:
        """输入校验失败时返回错误输出。"""
        nodes.append(
            QualityNodeFeedback(
                node="recommendation_generation",
                status="failed",
                message="输入校验失败，分析流程中止。",
            )
        )
        return QualityInspectionAgentOutput(
            summary="输入数据不完整，质量分析流程中止。",
            decision="standard_missing",
            evidence=["输入校验失败，请检查必填字段。"],
            next_actions=["补充质检批次信息和检验指标/缺陷记录后重试。"],
            node_feedback=nodes,
        )

    # ── plan() 兼容 BaseAgent ─────────────────────────────────

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        """BaseAgent 兼容入口。优先使用 execute() 处理结构化输入。"""
        return AgentResult(
            summary=f"质量检测智能体已接收请求：{request_text[:80]}",
            decision="quality_risk_detected",
            evidence=[
                "建议通过结构化接口 execute() 传入完整质检数据进行分析。",
            ],
            next_actions=[
                "提供质检批次信息（inspection_batch）",
                "提供检验指标列表（inspection_items）",
                "提供缺陷记录（defect_records）",
                "可选：提供质量标准（quality_standards）和历史缺陷（historical_defects）",
                "可选：提供现场上下文（context）以增强根因推断",
            ],
        )

    # ── 将内部 QualityNodeFeedback 映射为通用 NodeFeedback ─────

    def build_node_feedback(
        self, request_text: str, result: AgentResult
    ) -> list[NodeFeedback]:
        """兼容 BaseAgent / orchestrator 的节点反馈构建。"""
        now = datetime.now(tz=timezone.utc)
        return [
            NodeFeedback(
                node_id=f"{self.name}-intent",
                node_name="意图识别",
                status="completed",
                detail=f"已识别为{self.display_name}场景，请求内容：{request_text[:60]}",
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-analysis",
                node_name="规则分析",
                status="completed",
                detail=result.summary,
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-decision",
                node_name="决策输出",
                status="completed",
                detail=result.decision,
                started_at=now,
                completed_at=now,
            ),
        ]
