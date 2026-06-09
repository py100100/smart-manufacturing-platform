"""统一智能体注册中心。

固化五类智能体的名称、输入 Schema、输出 Schema，
确保所有智能体输出均包含 summary / decision / evidence / next_actions / node_feedback。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.agents.predictive_maintenance_agent import PredictiveMaintenanceAgent
from app.agents.process_parameter_optimization_agent import (
    ProcessParameterOptimizationAgent,
)
from app.agents.production_scheduling_agent import ProductionSchedulingAgent
from app.agents.quality_inspection_agent import QualityInspectionAgent
from app.agents.supply_chain_management_agent import SupplyChainManagementAgent
from app.schemas.agent import AgentName


@dataclass(slots=True)
class AgentMeta:
    """智能体元数据 — 名称、输入/输出 Schema。"""

    name: AgentName
    display_name: str
    scenario_hint: str
    input_schema: str  # 输入 Pydantic 类名
    output_schema: str  # 输出 Pydantic 类名
    agent: BaseAgent = field(repr=False)


class AgentRegistry:
    """五类智能体统一注册表。

    用法:
        registry = AgentRegistry()
        agent = registry.get("supply_chain_management")
        meta  = registry.meta("supply_chain_management")
        # meta.input_schema   → "app.schemas.supply_chain_management.SupplyChainManagementRequest"
        # meta.output_schema  → "app.schemas.supply_chain_management.SupplyChainManagementOutput"
    """

    def __init__(self) -> None:
        entries: list[AgentMeta] = [
            AgentMeta(
                name="production_scheduling",
                display_name="生产调度优化",
                scenario_hint="排产、工单、交期、产能、瓶颈、设备、工艺路线",
                input_schema="app.schemas.production_scheduling.ProductionSchedulingRequest",
                output_schema="app.schemas.production_scheduling.SchedulingAgentOutput",
                agent=ProductionSchedulingAgent(),
            ),
            AgentMeta(
                name="quality_inspection",
                display_name="质量检测与缺陷分析",
                scenario_hint="质量、质检、缺陷、不良、良率、根因、指标",
                input_schema="app.schemas.quality_inspection.QualityInspectionRequest",
                output_schema="app.schemas.quality_inspection.QualityInspectionAgentOutput",
                agent=QualityInspectionAgent(),
            ),
            AgentMeta(
                name="predictive_maintenance",
                display_name="设备预测性维护",
                scenario_hint="设备、振动、温度、电流、传感器、故障、维护、停机",
                input_schema="app.schemas.predictive_maintenance.PredictiveMaintenanceRequest",
                output_schema="app.schemas.predictive_maintenance.PredictiveMaintenanceOutput",
                agent=PredictiveMaintenanceAgent(),
            ),
            AgentMeta(
                name="supply_chain_management",
                display_name="供应链协同管理",
                scenario_hint="供应链、库存、采购、供应商、物料、BOM、缺料、积压",
                input_schema="app.schemas.supply_chain_management.SupplyChainManagementRequest",
                output_schema="app.schemas.supply_chain_management.SupplyChainManagementOutput",
                agent=SupplyChainManagementAgent(),
            ),
            AgentMeta(
                name="process_parameter_optimization",
                display_name="工艺参数优化",
                scenario_hint="工艺参数、质量优化、良品率、缺陷率、节拍、参数推荐",
                input_schema="app.schemas.process_parameter_optimization.ProcessParameterOptimizationRequest",
                output_schema="app.schemas.process_parameter_optimization.ProcessParameterOptimizationOutput",
                agent=ProcessParameterOptimizationAgent(),
            ),
        ]
        self._agents: dict[str, BaseAgent] = {e.name: e.agent for e in entries}
        self._meta: dict[str, AgentMeta] = {e.name: e for e in entries}

    # ── 查询 ──────────────────────────────────────────────────

    def get(self, name: str) -> BaseAgent:
        """按名称获取智能体实例。"""
        if name not in self._agents:
            available = list(self._agents.keys())
            raise KeyError(f"未知智能体 '{name}'，可用：{available}")
        return self._agents[name]

    def meta(self, name: str) -> AgentMeta:
        """按名称获取智能体元数据。"""
        if name not in self._meta:
            available = list(self._meta.keys())
            raise KeyError(f"未知智能体 '{name}'，可用：{available}")
        return self._meta[name]

    def all(self) -> dict[str, BaseAgent]:
        """返回 {name: agent} 映射。"""
        return dict(self._agents)

    def all_meta(self) -> list[AgentMeta]:
        """返回全部智能体元数据列表。"""
        return list(self._meta.values())

    def names(self) -> list[str]:
        """返回全部智能体名称。"""
        return list(self._agents.keys())

    # ── 输出契约校验 ──────────────────────────────────────────

    STANDARD_OUTPUT_FIELDS = (
        "summary",
        "decision",
        "evidence",
        "next_actions",
        "node_feedback",
    )

    @classmethod
    def verify_output_contract(cls, output_instance: object) -> list[str]:
        """校验输出实例是否包含标准字段。

        Returns:
            缺失字段列表（空列表表示通过）。
        """
        missing: list[str] = []
        for field in cls.STANDARD_OUTPUT_FIELDS:
            if not hasattr(output_instance, field):
                missing.append(field)
        return missing


# 模块级单例
_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """获取模块级注册表单例。"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
