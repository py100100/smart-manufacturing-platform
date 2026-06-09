from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROTECTED_MODULES = {
    "app/core/config.py": "配置层禁止硬编码真实密钥。",
    "app/db/session.py": "数据库层必须通过配置构造连接，不允许拼接真实生产凭据。",
    "app/services/deepseek_client.py": "模型调用层禁止打印密钥或完整响应体。",
    "hooks/check_claude.py": "Hook 规则必须保持 5 秒内可执行。",
}

FORBIDDEN_PATTERNS = {
    "eval(": "禁止使用 eval。",
    "exec(": "禁止使用 exec。",
    "DEEPSEEK_API_KEY=": "禁止把真实密钥写入代码。",
    "sk-": "禁止硬编码模型密钥。",
}


@dataclass(slots=True)
class GuardrailIssue:
    file_path: str
    message: str


def scan_text_for_guardrails(text: str, file_path: str = "snippet") -> list[GuardrailIssue]:
    issues: list[GuardrailIssue] = []
    for pattern, message in FORBIDDEN_PATTERNS.items():
        if pattern in text:
            issues.append(GuardrailIssue(file_path=file_path, message=message))
    return issues


def protected_module_hint(file_path: str) -> str | None:
    normalized = Path(file_path).as_posix()
    return PROTECTED_MODULES.get(normalized)
