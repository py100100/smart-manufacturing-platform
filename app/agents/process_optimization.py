from app.agents.base import AgentResult, BaseAgent


class ProcessOptimizationAgent(BaseAgent):
    name = "process_optimization"
    display_name = "工艺参数优化"
    scenario_hint = "工艺、参数、温度、压力、速度、优化"

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        process_name = context.get("process_name", "目标工艺")
        return AgentResult(
            summary=f"已对 {process_name} 的关键参数优化建立分析建议。",
            decision="建议采用参数分层试验设计，先稳定关键质量因子，再做局部寻优。",
            evidence=[
                "工艺优化需要优先识别关键质量参数之间的耦合关系。",
                "渐进式试验比一次性大范围调整更稳定。",
            ],
            next_actions=[
                "抽取历史工艺参数与质量结果。",
                "识别关键质量因子和控制窗口。",
                "生成下一轮优化参数组合。",
            ],
        )
