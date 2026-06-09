from app.agents.base import AgentResult, BaseAgent


class SupplyChainAgent(BaseAgent):
    name = "supply_chain"
    display_name = "供应链协同管理"
    scenario_hint = "采购、库存、缺料、供应商、交付"

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        stock_level = context.get("stock_level", "未知")
        return AgentResult(
            summary=f"已围绕库存水位 {stock_level} 评估供应链协同风险。",
            decision="建议按缺料风险优先级生成采购补货建议，并同步评估供应商交付稳定性。",
            evidence=[
                "制造供应链风险通常由缺料与交付波动共同触发。",
                "库存预警必须与排产需求联动。",
            ],
            next_actions=[
                "拉取未来两周生产计划。",
                "比对安全库存与在途库存。",
                "输出缺料清单和采购优先级。",
            ],
        )
