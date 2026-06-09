from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    async def generate(self, prompt: str) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "model": None,
                "content": "DeepSeek API Key 未配置，当前返回本地规则引擎结果。",
            }

        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是智能制造平台中的企业级分析助手，"
                        "需要给出结构化、可执行、可追溯的结论。"
                    ),
                },
                {"role": "user", "content": prompt},
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
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return {"model": self.settings.deepseek_model, "content": content}
