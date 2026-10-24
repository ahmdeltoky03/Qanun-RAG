"""Upstream 429/5xx are retried with backoff instead of surfacing as empty answers.

The Cohere trial tier answers 429 + Retry-After when the 20 req/min cap is hit; without
retries those became empty answers (faithfulness 0 rows) and mid-stream disconnects.
"""

from __future__ import annotations

import httpx
import pytest

from qanun.llm import OpenAICompatLLM

MSGS = [{"role": "user", "content": "q"}]


def _llm(settings) -> OpenAICompatLLM:
    s = settings.model_copy(
        update={"llm_provider": "openai", "llm_base_url": "http://llm.test", "llm_api_key": "k"}
    )  # fmt: skip
    return OpenAICompatLLM(s)


def _with_transport(llm, handler) -> OpenAICompatLLM:
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


async def test_complete_retries_429_then_succeeds(settings):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = _with_transport(_llm(settings), handler)
    assert await llm.complete(MSGS) == "ok"
    assert calls["n"] == 3


async def test_complete_gives_up_after_max_retries(settings):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503)

    llm = _with_transport(_llm(settings), handler)
    with pytest.raises(httpx.HTTPStatusError):
        await llm.complete(MSGS)
    assert calls["n"] == 5  # 1 attempt + 4 retries


async def test_stream_retries_429_then_streams(settings):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n'
        )  # fmt: skip

    llm = _with_transport(_llm(settings), handler)
    assert [t async for t in llm.stream(MSGS)] == ["hi"]
    assert calls["n"] == 2
