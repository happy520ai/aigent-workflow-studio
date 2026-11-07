# backend/llm_client.py —— T24：LLM 调用韧性层 + T31：SSE 流式
"""重试（指数退避 + 抖动，仅 429/5xx/超时，最多 2 次重试）、并发信号量
（LLM_MAX_CONCURRENCY 默认 2，对应讯飞等平台限流）、超时可配（LLM_TIMEOUT_S 默认 60s）。

transport_factory 为 T12 服务：每个真实尝试前重新解析并校验 api_base，返回按 IP 固定的
transport；factory 抛错视为确定性失败（不重试，直接降级）。

T31：chat_completion_stream 走 SSE（stream:true），逐段 yield 文本增量；
流式路径单次尝试（不重试），失败直接降级——增量语义下重放会造成重复输出。
"""
import asyncio
import json
import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    def __init__(
        self,
        max_concurrency: int | None = None,
        timeout_s: float | None = None,
        max_retries: int = 2,
    ):
        concurrency = max_concurrency if max_concurrency is not None else int(os.getenv("LLM_MAX_CONCURRENCY", "2"))
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._timeout = float(timeout_s if timeout_s is not None else os.getenv("LLM_TIMEOUT_S", "60"))
        self._max_retries = max_retries

    @staticmethod
    def _backoff(attempt: int) -> float:
        """指数退避 + 抖动：0.5s、1s（+0~0.25s 抖动）"""
        return 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.25)

    async def chat_completion(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        messages: list,
        max_tokens: int = 1024,
        transport_factory: Callable[[], Awaitable[httpx.AsyncBaseTransport]] | None = None,
    ) -> dict[str, Any]:
        attempt = 0
        last_error: str | None = None
        async with self._sem:
            while attempt <= self._max_retries:
                attempt += 1
                try:
                    kwargs: dict[str, Any] = {}
                    if transport_factory is not None:
                        kwargs["transport"] = await transport_factory()
                    async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, **kwargs) as client:
                        resp = await client.post(
                            f"{api_base}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": model, "messages": messages, "max_tokens": max_tokens},
                        )
                    if resp.status_code in RETRYABLE_STATUS and attempt <= self._max_retries:
                        last_error = f"HTTP {resp.status_code}"
                        await asyncio.sleep(self._backoff(attempt))
                        continue
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
                    return {"ok": True, "content": content, "degraded": False, "error": None, "attempts": attempt}
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = str(exc)
                    if attempt <= self._max_retries:
                        await asyncio.sleep(self._backoff(attempt))
                        continue
                except httpx.HTTPStatusError as exc:
                    last_error = f"HTTP {exc.response.status_code}" if exc.response is not None else str(exc)
                    status = exc.response.status_code if exc.response is not None else 0
                    if status in RETRYABLE_STATUS and attempt <= self._max_retries:
                        await asyncio.sleep(self._backoff(attempt))
                        continue
                    break  # 其余 4xx：确定性失败，不重试
                except Exception as exc:  # 含 transport_factory（T12 解析拒绝）——确定性失败
                    last_error = str(exc)
                    break
        return {"ok": False, "content": "", "degraded": True, "error": last_error, "attempts": attempt}

    async def chat_completion_stream(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        transport_factory: Callable[[], Awaitable[httpx.AsyncBaseTransport]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """T31：SSE 流式对话。逐段 yield {delta, done, degraded, error}；结束段 done=True。
        单次尝试：任何失败以 degraded=True 收尾（由调用方走降级路径）。"""
        async with self._sem:
            try:
                kwargs: dict[str, Any] = {}
                if transport_factory is not None:
                    kwargs["transport"] = await transport_factory()
                async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, **kwargs) as client:
                    async with client.stream(
                        "POST",
                        f"{api_base}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True},
                    ) as resp:
                        if resp.status_code != 200:
                            await resp.aread()
                            yield {"delta": "", "done": True, "degraded": True, "error": f"HTTP {resp.status_code}"}
                            return
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                            except (ValueError, IndexError, AttributeError):
                                continue
                            if delta:
                                yield {"delta": delta, "done": False, "degraded": False, "error": None}
                yield {"delta": "", "done": True, "degraded": False, "error": None}
            except Exception as exc:
                yield {"delta": "", "done": True, "degraded": True, "error": str(exc)}
