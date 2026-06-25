import pytest

from app.schemas.agent import AgentTaskRequest, TokenUsage
from app.services.deepseek_client import DeepSeekClient
from app.services.orchestrator import AgentOrchestrator


class FakeUsageLLM:
    is_configured = True

    def __init__(self) -> None:
        self.token_usage = TokenUsage()

    def reset_token_usage(self) -> None:
        self.token_usage = TokenUsage()

    async def generate_with_system_prompt(
        self, system_prompt: str, user_prompt: str
    ) -> dict:
        self.token_usage = TokenUsage(
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
            request_count=1,
        )
        return {
            "model": "fake-model",
            "content": (
                "【问题直接回答】设备振动异常需要结合质量、设备、工艺和生产数据进行闭环分析，"
                "核心目标是降低误报、漏报并提前识别维护风险。系统应先建立健康基线，再用"
                "SPC、EWMA、CUSUM 和趋势预测模型识别异常，最后把结果转化为维护工单和复核动作。"
                "\n【方法步骤】\n"
                "1. 采集振动、温度、电流和设备运行状态，按产线、班次和设备编号建立数据基线。\n"
                "2. 使用统计过程控制识别短期异常，并对超过控制限的点进行质量缺陷关联分析。\n"
                "3. 使用趋势模型判断振动是否持续恶化，区分偶发波动和真实设备退化。\n"
                "4. 将异常窗口与质检缺陷、工艺参数、换料记录关联，定位根因链路。\n"
                "5. 对高风险设备生成维护工单，并设置复检、备件、停机窗口和责任人。\n"
                "6. 将人工确认结果回写系统，持续校准报警阈值，降低误报和漏报。\n"
                "\n【实施建议】\n"
                "- 先选择关键设备做试点，连续采集不少于三十天的健康运行数据。\n"
                "- 对质量缺陷率、设备健康指数和停机时间建立统一看板。\n"
                "- 对高风险设备设置预警分级，避免所有异常都直接升级为紧急工单。\n"
                "\n【风险控制】\n"
                "- 如果样本不足，模型容易把正常工况切换误判为设备故障。\n"
                "- 如果缺少人工确认闭环，阈值无法持续优化，误报和漏报会反复出现。"
            ),
        }


def test_deepseek_client_accumulates_token_usage() -> None:
    client = DeepSeekClient()

    client._record_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    )
    client._record_usage(
        {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    )

    assert client.token_usage.prompt_tokens == 17
    assert client.token_usage.completion_tokens == 8
    assert client.token_usage.total_tokens == 25
    assert client.token_usage.request_count == 2


@pytest.mark.asyncio
async def test_orchestrator_exposes_llm_token_usage(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.orchestrator.MemoryStore.append",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator.KnowledgeService.retrieve",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.orchestrator.KnowledgeService.add_case",
        lambda *args, **kwargs: None,
    )

    orchestrator = AgentOrchestrator(llm_client=FakeUsageLLM())
    response = await orchestrator.execute(
        AgentTaskRequest(
            request_text="如何分析设备振动异常并降低误报漏报风险",
            agent_name="predictive_maintenance",
        )
    )

    assert response.token_usage.prompt_tokens == 120
    assert response.token_usage.completion_tokens == 80
    assert response.token_usage.total_tokens == 200
    assert response.token_usage.request_count == 1
