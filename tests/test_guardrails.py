from app.core.guardrails import scan_text_for_guardrails


def test_guardrail_detects_forbidden_pattern() -> None:
    issues = scan_text_for_guardrails("token = 'sk-test'")

    assert len(issues) == 1
    assert "密钥" in issues[0].message
