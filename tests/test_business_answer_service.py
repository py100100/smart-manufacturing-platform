"""业务问答增强层 — 独立单元测试。

验证 BusinessAnswerService 的领域识别、答案生成、质量验证。
"""
from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════
# 领域检测
# ══════════════════════════════════════════════════════════════════


class TestBusinessDomainDetection:
    """验证业务领域和知识领域的检测逻辑。"""

    def test_production_scheduling_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains(
            "订单交期集中但设备产能不足，如何优化排产？"
        )
        assert domains.get("production_scheduling", False)

    def test_quality_inspection_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains(
            "最近批次缺陷率上升，主要缺陷为尺寸偏差和表面粗糙度异常"
        )
        assert domains.get("quality_inspection", False)

    def test_simple_quality_nonconformance_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains("零件质量不达标")
        assert domains.get("quality_inspection", False)

    def test_predictive_maintenance_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains(
            "设备振动传感器读数持续升高，如何判断是否需要维护？"
        )
        assert domains.get("predictive_maintenance", False)

    def test_supply_chain_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains(
            "如何根据库存、BOM和在途采购判断缺料风险？"
        )
        assert domains.get("supply_chain_management", False)

    def test_process_optimization_domain_detected(self) -> None:
        from app.services.business_answer_service import _detect_business_domains
        domains = _detect_business_domains(
            "如何根据质量反馈优化工艺参数？"
        )
        assert domains.get("process_parameter_optimization", False)


# ══════════════════════════════════════════════════════════════════
# 解释型问题识别
# ══════════════════════════════════════════════════════════════════


class TestBusinessExplanationDetection:
    """验证 _is_business_explanation_question 对五大业务问题的识别。"""

    @pytest.mark.parametrize("text, expected", [
        ("如何优化排产计划提升产能？", True),
        ("怎么判断库存是否缺料？", True),
        ("为什么最近缺陷率上升了？", True),
        ("请分析设备故障的根本原因", True),
        ("如何提高良品率？", True),
        ("怎样优化工艺参数提升良品率？", True),
        ("订单交期集中在本周，但关键设备产能不足，如何优化生产排程？", True),
        ("基于振动、温度、电流数据，如何预测设备剩余寿命？", True),
        # 不应判定的
        ("今天天气不错", False),
        ("设备CNC-001振动传感器报警", False),
        ("你好", False),
    ])
    def test_is_business_explanation(self, text: str, expected: bool) -> None:
        from app.services.business_answer_service import (
            _is_business_explanation_question,
        )
        assert _is_business_explanation_question(text) == expected, (
            f"text={text!r}, expected={expected}"
        )


# ══════════════════════════════════════════════════════════════════
# BusinessAnswerService.generate_answer 离线测试
# ══════════════════════════════════════════════════════════════════


class FakeLLMClient:
    """伪造 LLM 客户端 — 任何调用都记录并返回空。"""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def is_configured(self) -> bool:
        return True

    async def generate_with_system_prompt(
        self, system_prompt: str, user_prompt: str
    ) -> dict:
        self.call_count += 1
        return {"content": ""}


class TestBusinessAnswerServiceOffline:
    """验证离线模式下各领域能生成合格答案。"""

    @pytest.mark.asyncio
    async def test_all_five_domains_generate_valid_answers(self) -> None:
        from app.services.business_answer_service import (
            BusinessAnswerService,
            validate_summary,
        )

        svc = BusinessAnswerService(llm_client=FakeLLMClient())
        questions = [
            ("如何优化排产计划提升产能？", ["production_scheduling"]),
            ("最近缺陷率上升，如何分析根因？", ["quality_inspection"]),
            ("如何判断设备是否需要预测性维护？", ["predictive_maintenance"]),
            ("如何根据BOM和库存计算缺料风险？", ["supply_chain_management"]),
            ("如何优化工艺参数提升良品率？", ["process_parameter_optimization"]),
        ]

        for text, agents in questions:
            answer = await svc.generate_answer(text, agents, use_llm=False)
            assert answer is not None, f"离线应答失败: {text!r}"
            assert len(answer) > 200, f"答案过短: {text!r}"
            is_valid, violations = validate_summary(answer)
            assert is_valid, (
                f"答案未通过质量验证: {text!r}\n"
                + "\n".join(violations)
            )

    @pytest.mark.asyncio
    async def test_offline_require_llm_false_never_calls_llm(self) -> None:
        from app.services.business_answer_service import BusinessAnswerService

        fake_llm = FakeLLMClient()
        svc = BusinessAnswerService(llm_client=fake_llm)

        await svc.generate_answer(
            "如何根据库存和BOM判断缺料风险？",
            agent_names=["supply_chain_management"],
            use_llm=False,
        )
        assert fake_llm.call_count == 0, (
            f"require_llm=False 时不应调用 LLM，但调用了 {fake_llm.call_count} 次"
        )

    @pytest.mark.asyncio
    async def test_offline_answers_never_contain_hollow_markers(self) -> None:
        from app.services.business_answer_service import BusinessAnswerService

        svc = BusinessAnswerService(llm_client=None)
        questions = [
            "如何优化排产计划提升产能？",
            "最近缺陷率上升，如何分析根因？",
            "如何判断设备是否需要预测性维护？",
            "如何根据BOM和库存计算缺料风险？",
            "如何优化工艺参数提升良品率？",
        ]

        hollow_markers = [
            "智能体已接收请求", "请提供完整数据",
            "系统调度了", "协同分析完成",
            "建议按优先级处理",
        ]

        for q in questions:
            # 用空 agent_names 让 generate_answer 走本地模板路径
            answer = await svc.generate_answer(q, [], use_llm=False)
            if answer is None:
                continue
            for marker in hollow_markers:
                assert marker not in answer, (
                    f"答案包含禁止短语 '{marker}': {q!r}"
                )

    @pytest.mark.asyncio
    async def test_simple_quality_nonconformance_answer_is_actionable(self) -> None:
        from app.services.business_answer_service import (
            BusinessAnswerService,
            validate_summary,
        )

        svc = BusinessAnswerService(llm_client=None)
        answer = await svc.generate_answer(
            "零件质量不达标",
            ["quality_inspection"],
            use_llm=False,
        )

        assert answer is not None
        for keyword in ["隔离", "复检", "不建议放行", "根因", "后续行动"]:
            assert keyword in answer
        assert "SPC 动态控制限" not in answer
        assert "知识图谱" not in answer

        is_valid, violations = validate_summary(answer)
        assert is_valid, "\n".join(violations)
