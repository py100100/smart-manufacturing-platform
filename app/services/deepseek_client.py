from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.agent import TokenUsage


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._token_usage_var: ContextVar[TokenUsage] = ContextVar(
            "deepseek_token_usage",
            default=TokenUsage(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    @property
    def token_usage(self) -> TokenUsage:
        return self._token_usage_var.get()

    def reset_token_usage(self) -> None:
        self._token_usage_var.set(TokenUsage())

    def _record_usage(self, usage: dict[str, Any] | None) -> TokenUsage:
        if not usage:
            return self.token_usage

        current = self.token_usage
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or prompt_tokens + completion_tokens
        )
        updated = TokenUsage(
            prompt_tokens=current.prompt_tokens + prompt_tokens,
            completion_tokens=current.completion_tokens + completion_tokens,
            total_tokens=current.total_tokens + total_tokens,
            request_count=current.request_count + 1,
        )
        self._token_usage_var.set(updated)
        return updated

    async def generate(self, prompt: str) -> dict[str, Any]:
        """默认生成 — 使用企业分析助手 system prompt。"""
        return await self.generate_with_system_prompt(
            "你是智能制造平台中的企业级分析助手，"
            "需要给出结构化、可执行、可追溯的结论。",
            prompt,
        )

    async def generate_with_system_prompt(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """带自定义 system prompt 的生成 — 用于知识问答等场景。"""
        if not self.is_configured:
            return {
                "model": None,
                "usage": self.token_usage.model_dump(),
                "content": "DeepSeek API Key 未配置，当前返回本地规则引擎结果。",
            }

        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.request_timeout_seconds,
        ) as client:
            response = await client.post(
                "/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = self._record_usage(data.get("usage"))
        return {
            "model": self.settings.deepseek_model,
            "content": content,
            "usage": usage.model_dump(),
        }
