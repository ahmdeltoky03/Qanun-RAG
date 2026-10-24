"""LLM clients. Anything that speaks the OpenAI chat API works (vLLM, Ollama, OpenAI)."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from qanun.arabic import has_arabic
from qanun.config import Settings

# Transient upstream statuses worth retrying (trial-tier rate limits answer 429 + Retry-After).
_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4


def _retry_delay(r: httpx.Response, attempt: int) -> float:
    """Honour Retry-After when the server sends it; otherwise exponential backoff capped at 30s."""
    try:
        return min(float(r.headers.get("Retry-After")), 60.0)
    except (TypeError, ValueError):
        return min(1.5 * 2**attempt, 30.0)


SYSTEM_AR = (
    "أنت مساعد قانوني متخصص في القانون المدني المصري. أجب فقط اعتمادًا على نصوص المواد المرفقة في السياق، "
    "ولا تستخدم أي معلومة من خارجها. اذكر رقم كل مادة تعتمد عليها بين أقواس مربعة بهذا الشكل: [المادة 147]. "
    "إذا لم تكفِ النصوص للإجابة فقل صراحةً: «لم أجد في نصوص القانون المرفقة ما يجيب عن هذا السؤال». "
    "إذا كانت المادة ملغاة فاذكر ذلك. هذه معلومات عامة وليست استشارة قانونية. "
    "اكتب الإجابة بالعربية فقط، ولا تستخدم أي حروف أو كلمات بلغة أخرى (كالصينية مثلًا). "
    "إذا احتوى السياق على مواد ذات صلة فاستخلص الإجابة منها ولو تطلّب ذلك الجمع بين أكثر من مادة، "
    "ولا تقل «لم أجد» إلا إذا لم يوجد أي نص ذي صلة فعلًا. "
    "التزم بألفاظ نصوص المواد نفسها ما أمكن ولا تعد صياغتها بمرادفات من عندك، "
    "ولا تضف عبارات حشو أو نسب من خارج السياق مثل «وفقًا للمادة كذا من القانون المدني المصري» أو «بناءً على النصوص المرفقة»؛ "
    "الإحالة بين أقواس مربعة تكفي عن أي صيغة نسب في متن الكلام. "
    "لا تعلّق على طريقة إعداد الإجابة ولا تذكر أنك ترجمت أو لخصت أو استخلصت. "
    "أجب مباشرةً دون تمهيد ودون شرح طريقة تفكيرك، ولا تبدأ بعبارات مثل «يسأل المستخدم» أو «نحتاج إلى». وباختصار."
)
SYSTEM_EN = (
    "You are a legal assistant for the Egyptian Civil Code. Answer ONLY from the article texts in the context. "
    "Cite every article you rely on in square brackets like [Article 147]. If the context is insufficient, say: "
    '"I could not find an answer in the provided Civil Code text." If an article is repealed, say so. '
    "This is general information, not legal advice. "
    "Write the answer in English only, using no characters or words from any other language. "
    "If the context contains relevant articles, derive the answer from them even if that means combining "
    'several articles; say "I could not find" only when no relevant text exists at all. '
    "Keep the articles' own wording wherever possible instead of paraphrasing with your own synonyms, "
    "and add no filler attribution from outside the context such as 'according to Article X of the Egyptian "
    "Civil Code' or 'based on the provided texts'; the square-bracket citation is attribution enough. "
    "Never comment on how you produced the answer (no remarks about translating, summarising or deriving). "
    "Answer directly with no preamble and no reasoning narration; never open with phrases like "
    '"The user asks" or "We need to". Be concise.'
)
NOT_FOUND_AR = "لم أجد في نصوص القانون المرفقة ما يجيب عن هذا السؤال."
NOT_FOUND_EN = "I could not find an answer in the provided Civil Code text."


def build_messages(question: str, items: list) -> list[dict]:
    ar = has_arabic(question)
    blocks = []
    for it in items:
        head = f"[المادة {it.article_number}]" if ar else f"[Article {it.article_number}]"
        flag = " (ملغاة)" if (ar and it.is_repealed) else " (repealed)" if it.is_repealed else ""
        # Send only the question's language: halves the prompt (faster prefill, less
        # cross-language distraction). Fall back to the other language if this one is empty.
        body = ((it.text_ar if ar else it.text_en) or (it.text_en if ar else it.text_ar) or "").strip()
        blocks.append(f"{head}{flag}\n{body}".strip())
    context = "\n\n".join(blocks)
    label = "السياق" if ar else "Context"
    q_label = "السؤال" if ar else "Question"
    return [
        {"role": "system", "content": SYSTEM_AR if ar else SYSTEM_EN},
        {"role": "user", "content": f"{label}:\n{context}\n\n{q_label}: {question}"},
    ]


class LLM(Protocol):
    name: str

    async def complete(self, messages: list[dict]) -> str: ...
    def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...


class FakeLLM:
    """Extractive stand-in used offline and in tests: quotes the best-matching article."""

    name = "fake-extractive"

    async def complete(self, messages: list[dict]) -> str:
        user = messages[-1]["content"]
        ar = SYSTEM_AR in messages[0]["content"]
        m = re.search(r"\[(?:المادة|Article) (\d+)\][^\n]*\n(.+?)(?:\n\n|\nالسؤال|\nQuestion|$)", user, re.S)
        if not m:
            return NOT_FOUND_AR if ar else NOT_FOUND_EN
        body = " ".join(m.group(2).split("\n")[:1] if ar else m.group(2).split("\n")[-1:]).strip()
        return f"{body[:400]} [{'المادة' if ar else 'Article'} {m.group(1)}]"

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        for tok in (await self.complete(messages)).split(" "):
            yield tok + " "


class OpenAICompatLLM:
    def __init__(self, s: Settings):
        self.name = s.llm_model
        self._url = s.llm_base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {s.llm_api_key}"}
        self._body = {"model": s.llm_model, "temperature": s.llm_temperature, "max_tokens": s.llm_max_tokens}
        if s.llm_keep_alive:
            # Ollama rejects a bare "-1" string ("missing unit in duration") but
            # accepts the int -1, and accepts unit strings like "30m". Send ints as ints.
            ka = s.llm_keep_alive.strip()
            self._body["keep_alive"] = int(ka) if ka.lstrip("-").isdigit() else ka
        self._timeout = s.llm_timeout_s
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        # One pooled client for the app's lifetime: keeps keep-alive connections to
        # the model server warm and avoids per-request TLS/TCP setup latency.
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def complete(self, messages: list[dict]) -> str:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES + 1):
            r = await client.post(self._url, headers=self._headers, json={**self._body, "messages": messages})
            if r.status_code not in _RETRYABLE or attempt == _MAX_RETRIES:
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            await asyncio.sleep(_retry_delay(r, attempt))  # rate-limited: back off, then retry
        raise AssertionError("unreachable")

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES + 1):
            async with client.stream(
                "POST",
                self._url,
                headers=self._headers,
                json={**self._body, "messages": messages, "stream": True},
            ) as r:
                # The status arrives before any token is yielded, so retrying here is safe.
                if r.status_code in _RETRYABLE and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_retry_delay(r, attempt))
                    continue
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
            return

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def get_llm(s: Settings) -> LLM:
    if s.llm_provider == "fake":
        return FakeLLM()
    if s.llm_provider in ("openai", "vllm", "ollama"):
        return OpenAICompatLLM(s)
    raise ValueError(f"unknown llm provider: {s.llm_provider}")
