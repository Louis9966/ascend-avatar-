"""Streaming LLM client (OpenAI-compatible)."""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, List

import httpx


class LLMClient:
    """Async OpenAI-compatible streaming chat client."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "qwen3_32b",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )

    @staticmethod
    def build_messages(
        history: List[dict[str, str]], user_text: str
    ) -> List[dict[str, str]]:
        """Build message list from conversation history and new user input."""
        messages: List[dict[str, str]] = []
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_text})
        return messages

    async def chat_stream(
        self,
        messages: List[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncIterator[tuple[str, dict]]:
        """Yield (delta_text, metadata) tuples.

        metadata keys include first_token_latency_ms and finish_reason.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        start = time.perf_counter()
        first_token_time: float | None = None

        async with self.client.stream(
            "POST", "/chat/completions", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):].strip()
                if data == "[DONE]":
                    break
                try:
                    import json

                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content", "")
                if text:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    meta = {
                        "first_token_latency_ms": round(
                            (first_token_time - start) * 1000, 1
                        ),
                        "finish_reason": choices[0].get("finish_reason"),
                    }
                    yield text, meta

    async def healthcheck(self) -> bool:
        try:
            resp = await self.client.get("/models", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self.client.aclose()


if __name__ == "__main__":

    async def _test():
        client = LLMClient(
            base_url="http://192.168.1.117:1025/v1",
            model="qwen3_32b",
        )
        messages = [{"role": "user", "content": "请用一句话介绍自己"}]
        async for text, meta in client.chat_stream(messages, max_tokens=30):
            print(text, end="", flush=True)
        print("\nmeta:", meta)
        await client.close()

    asyncio.run(_test())
