"""业务闭环服务 — 将智能体编排输出转化为可执行的业务对象。

内存级实现，不依赖数据库。后续可接入持久化层。
"""

from __future__ import annotations

from app.schemas.agent import AgentStep, NodeFeedback, OrchestrationResponse
from app.schemas.business_closure import (
    ActionItem,
    Alert,
    BusinessClosure,
    Report,
    WorkOrder,
)

# ── 决策到预警的映射规则 ────────────────────────────────────

_DECISION_ALERT_RULES: list[tuple[list[str], str, str, str]] = [
    # (match_keywords, severity, alert_type, title_template)
    (["safety_risk", "安全"], "critical", "safety", "安全风险预警"),
    (["critical_shortage", "严重缺料", "紧急采购"], "critical", "supply", "严重缺料预警"),
    (["supplier_risk", "供应商风险", "供应商.*风险"], "warning", "supply", "供应商风险预警"),
    (["shortage_risk", "缺料风险", "缺料"], "warning", "supply", "缺料风险预警"),
    (["quality_risk", "质量风险", "缺陷.*风险", "良率.*低"], "warning", "quality", "质量风险预警"),
    (["parameter_out_of_range", "参数越界", "参数.*超出"], "warning", "process", "工艺参数越界预警"),
    (["conflicting_targets", "目标冲突", "冲突"], "warning", "process", "目标冲突预警"),
    (["po_delay", "延期", "逾期"], "warning", "supply", "采购延期预警"),
    (["overstock", "积压"], "info", "supply", "库存积压预警"),
    # 中文关键词兜底
    (["设备.*故障", "设备.*异常", "设备.*风险", "停机"], "critical", "maintenance", "设备故障预警"),
    (["维护", "振动"], "warning", "maintenance", "设备维护预警"),
]


def _decision_to_alert_key(text: str) -> str | None:
    """将决策/摘要字符串映射到预警规则 key。"""
    import re
    for keywords, _, _, _ in _DECISION_ALERT_RULES:
        for kw in keywords:
            if re.search(kw, text):
                return keywords[0]  # 返回第一个关键词作为 key
    return None


def _lookup_alert_rule(key: str) -> tuple[str, str, str] | None:
    """按 key 查找预警规则。"""
    for keywords, severity, alert_type, title in _DECISION_ALERT_RULES:
        if keywords[0] == key:
            return (severity, alert_type, title)
    return None


class BusinessClosureService:
    """业务闭环服务 — 将 OrchestrationResponse 转化为 BusinessClosure。"""

    @staticmethod
    def build_closure(response: OrchestrationResponse) -> BusinessClosure:
        """从编排响应生成完整业务闭环对象。"""
        alerts = BusinessClosureService._extract_alerts(response)
        work_orders = BusinessClosureService._extract_work_orders(response)
        reports = BusinessClosureService._extract_reports(response)
        action_items = BusinessClosureService._extract_action_items(response)

        return BusinessClosure(
            alerts=alerts,
            work_orders=work_orders,
            reports=reports,
            action_items=action_items,
        )

    # ── 预警提取 ─────────────────────────────────────────

    @staticmethod
    def _extract_alerts(response: OrchestrationResponse) -> list[Alert]:
        alerts: list[Alert] = []

        for step in response.agent_chain:
            # 同时检查 decision 和 summary 中的风险关键词
            combined = f"{step.decision} {step.summary}"
            key = _decision_to_alert_key(combined)
            if key is None:
                # agent_name 也可以推断预警类型
                if "maintenance" in step.agent_name or "维护" in step.display_name:
                    key = "维护"  # 兜底设备维护预警
                else:
                    continue

            rule = _lookup_alert_rule(key)
            if rule is None:
                continue
            severity, alert_type, title = rule

            alerts.append(
                Alert(
                    source_agent=step.agent_name,
                    severity=severity,
                    alert_type=alert_type,
                    title=title,
                    message=f"[{step.display_name}] {step.summary}",
                )
            )

        # 协同模式下额外追加一条综合风险提示
        if response.execution_mode == "collaborative" and len(response.agent_chain) >= 2:
            risk_decisions = [
                s.decision
                for s in response.agent_chain
                if _decision_to_alert_key(f"{s.decision} {s.summary}")
            ]
            if risk_decisions:
                alerts.append(
                    Alert(
                        source_agent="+".join(
                            s.agent_name for s in response.agent_chain
                        ),
                        severity="warning",
                        alert_type="process",
                        title="多智能体协同风险提示",
                        message=f"协同链检测到 {len(risk_decisions)} 个风险决策：{'；'.join(risk_decisions)}",
                    )
                )

        return alerts

    # ── 工单提取 ─────────────────────────────────────────

    @staticmethod
    def _extract_work_orders(response: OrchestrationResponse) -> list[WorkOrder]:
        orders: list[WorkOrder] = []
        import re

        for step in response.agent_chain:
            combined = f"{step.decision} {step.summary}"
            agent = step.agent_name

            # 维护工单
            if agent == "predictive_maintenance" or "维护" in step.display_name:
                orders.append(
                    WorkOrder(
                        source_agent=agent,
                        order_type="maintenance",
                        title=f"设备维护工单 — {step.display_name}",
                        description=step.summary,
                        priority=(
                            "urgent" if re.search(r"safety|安全|停机|故障|紧急", combined)
                            else "high"
                        ),
                        target_entity="待指定设备",
                        suggested_timing=(
                            "立即" if re.search(r"safety|安全|停机|紧急", combined)
                            else "48小时内"
                        ),
                    )
                )

            # 采购工单
            if agent == "supply_chain_management" or "供应链" in step.display_name:
                if re.search(r"shortage|critical|缺料|采购|库存|物料", combined):
                    orders.append(
                        WorkOrder(
                            source_agent=agent,
                            order_type="purchase",
                            title=f"采购工单 — {step.display_name}",
                            description=step.summary,
                            priority=(
                                "urgent" if re.search(r"critical|严重|紧急", combined)
                                else "high"
                            ),
                            target_entity="待指定物料",
                            suggested_timing=(
                                "立即" if re.search(r"critical|严重|紧急", combined)
                                else "7日内"
                            ),
                        )
                    )

            # 工艺优化工单
            if agent == "process_parameter_optimization" or "工艺" in step.display_name:
                if re.search(r"recommended|optim|out_of_range|越界|优化|参数", combined):
                    orders.append(
                        WorkOrder(
                            source_agent=agent,
                            order_type="optimization",
                            title=f"工艺优化工单 — {step.display_name}",
                            description=step.summary,
                            priority=(
                                "high" if re.search(r"out_of_range|越界|安全", combined)
                                else "medium"
                            ),
                            target_entity="待指定工艺参数",
                            suggested_timing="本月内",
                        )
                    )

            # 质检工单
            if agent == "quality_inspection" or "质量" in step.display_name:
                if re.search(r"risk|质量|缺陷|不良|良率", combined):
                    orders.append(
                        WorkOrder(
                            source_agent=agent,
                            order_type="inspection",
                            title=f"质检工单 — {step.display_name}",
                            description=step.summary,
                            priority="high",
                            target_entity="待指定批次",
                            suggested_timing="24小时内",
                        )
                    )

            # 排产工单 — 当检测到瓶颈或交期风险时
            if agent == "production_scheduling" or "排产" in step.display_name:
                if re.search(r"瓶颈|交期|产能|优化", combined):
                    orders.append(
                        WorkOrder(
                            source_agent=agent,
                            order_type="optimization",
                            title=f"排产调整工单 — {step.display_name}",
                            description=step.summary,
                            priority="medium",
                            target_entity="待指定产线",
                            suggested_timing="本周内",
                        )
                    )

        return orders

    # ── 报告提取 ─────────────────────────────────────────

    @staticmethod
    def _extract_reports(response: OrchestrationResponse) -> list[Report]:
        reports: list[Report] = []

        # 每个 agent 一份报告
        for step in response.agent_chain:
            reports.append(
                Report(
                    source_agents=[step.agent_name],
                    title=f"{step.display_name} — 分析报告",
                    summary=step.summary,
                    findings=list(step.evidence),
                    recommendations=list(step.next_actions),
                )
            )

        # 协同模式：额外生成综合报告
        if response.execution_mode == "collaborative" and len(response.agent_chain) >= 2:
            all_agents = [s.agent_name for s in response.agent_chain]
            all_findings: list[str] = []
            all_recs: list[str] = []
            for s in response.agent_chain:
                all_findings.extend(s.evidence)
                all_recs.extend(s.next_actions)

            reports.append(
                Report(
                    source_agents=all_agents,
                    title="多智能体协同分析 — 综合报告",
                    summary=response.summary,
                    findings=all_findings,
                    recommendations=all_recs,
                )
            )

        return reports

    # ── 行动项提取 ───────────────────────────────────────

    @staticmethod
    def _extract_action_items(response: OrchestrationResponse) -> list[ActionItem]:
        items: list[ActionItem] = []

        for step in response.agent_chain:
            priority = BusinessClosureService._infer_priority(step.decision)
            for action_text in step.next_actions:
                items.append(
                    ActionItem(
                        source_agent=step.agent_name,
                        description=action_text,
                        priority=priority,
                    )
                )

        # 去重
        seen: set[str] = set()
        unique: list[ActionItem] = []
        for item in items:
            key = f"{item.source_agent}|{item.description}"
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    @staticmethod
    def _infer_priority(decision: str) -> str:
        import re
        if re.search(r"critical|urgent|safety|严重|紧急|安全", decision):
            return "urgent"
        if re.search(r"risk|out_of_range|风险|越界|异常|缺料|缺陷", decision):
            return "high"
        if re.search(r"recommended|optim|建议|优化|推荐", decision):
            return "medium"
        return "low"
