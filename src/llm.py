"""
LLMClient — 统一的 DashScope LLM 调用封装
"""
import os
import json
import httpx
import logging
from typing import AsyncGenerator

logger = logging.getLogger("nous.llm")


class LLMClient:
    """DashScope qwen-plus 调用封装，支持流式和非流式"""

    def __init__(self):
        self.base_url = os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.model = os.getenv("NOUS_MODEL", "qwen-plus")

        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY 未设置！")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式对话，逐个 yield token 文本片段"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(f"LLM 调用失败 [{response.status_code}]: {body}")
                    yield f"[错误] LLM 调用失败: {response.status_code}"
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        content = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def chat(self, messages: list[dict]) -> str:
        """非流式对话，返回完整回复文本（用于记忆提取等内部调用）"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            if response.status_code != 200:
                logger.error(
                    f"LLM 调用失败 [{response.status_code}]: {response.text}"
                )
                return ""
            try:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"LLM 响应解析失败: {e}")
                return ""
