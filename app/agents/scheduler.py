from app.agents.base import AgentResult, BaseAgent


class SchedulerAgent(BaseAgent):
    name = "scheduler"
    display_name = "生产调度优化"
    scenario_hint = "排产、工单、交期、产能、瓶颈"

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        order_count = context.get("order_count", "未提供")
        line_load = context.get("line_load", "未知")
        return AgentResult(
            summary=f"基于订单数 {order_count} 和产线负载 {line_load} 完成排产分析。",
            decision="优先采用交期优先 + 瓶颈工序前置的混合排产策略。",
            evidence=[
                "调度类请求通常需要先识别交期风险和瓶颈资源。",
                "上下文已包含订单规模或负载信息，可用于快速分级。",
            ],
            next_actions=[
                "核对关键设备可用工时。",
                "将瓶颈工序提前锁定。",
                "生成可执行的日排产清单。",
            ],
        )
