from app.agents.base import AgentResult, BaseAgent


class MaintenanceAgent(BaseAgent):
    name = "maintenance"
    display_name = "设备预测性维护"
    scenario_hint = "设备、故障、停机、振动、温度、电流、维护"

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        equipment = context.get("equipment", "关键设备")
        return AgentResult(
            summary=f"已对 {equipment} 的健康状态开展维护推演。",
            decision="建议采用阈值预警 + 趋势预测双策略，先处理高停机风险设备。",
            evidence=[
                "预测性维护核心是监控异常趋势而非只看单点阈值。",
                "高价值设备的异常应优先转工单。",
            ],
            next_actions=[
                "接入近 7 天振动与温度数据。",
                "比对故障代码与历史保养记录。",
                "自动生成预防性维护工单。",
            ],
        )
