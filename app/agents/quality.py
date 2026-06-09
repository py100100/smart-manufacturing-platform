from app.agents.base import AgentResult, BaseAgent


class QualityAgent(BaseAgent):
    name = "quality"
    display_name = "质量检测与缺陷分析"
    scenario_hint = "质量、缺陷、不良、良率、根因"

    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        defect_rate = context.get("defect_rate", "未知")
        return AgentResult(
            summary=f"已围绕缺陷率 {defect_rate} 建立质量问题初步分析。",
            decision="建议从人机料法环五个维度开展 8D 根因分析，并先锁定高频缺陷。",
            evidence=[
                "缺陷分析需要结合标准、批次和工艺参数交叉判断。",
                "高频缺陷优先处理可最快降低不良率。",
            ],
            next_actions=[
                "抽取最近三批次质检记录。",
                "按缺陷类型聚类统计。",
                "建立整改责任人与验证计划。",
            ],
        )
