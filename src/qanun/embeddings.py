"""Embedding providers behind one tiny interface.

`hashing` needs no network and no model download (character n-gram feature hashing),
which keeps tests, CI and offline demos deterministic. Real deployments use a
multilingual model (Cohere, an OpenAI-compatible endpoint, or sentence-transformers).
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Protocol

import anyio
import httpx
import numpy as np

from qanun.arabic import normalize_for_search
from qanun.config import Settings


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...
    async def aembed_query(self, text: str) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.clip(n, 1e-12, None)


class HashingEmbedder:
    """Signed feature hashing over word unigrams + char 3/4-grams (deterministic, offline)."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing-{dim}"

    @staticmethod
    def _features(text: str) -> list[str]:
        text = normalize_for_search(text)
        words = re.findall(r"\w+", text)
        feats = [f"w:{w}" for w in words]
        for w in words:
            padded = f"#{w}#"
            for n in (3, 4):
                feats += [f"c{n}:{padded[i : i + n]}" for i in range(max(len(padded) - n + 1, 0))]
        return feats

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for f in self._features(text):
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _l2(np.stack([self._vec(t) for t in texts])) if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return _l2(self._vec(text))

    async def aembed_query(self, text: str) -> np.ndarray:
        return self.embed_query(text)


def _post_with_retry(
    url: str, *, headers: dict, json: dict, timeout: float = 60.0, attempts: int = 4
) -> httpx.Response:
    """POST that retries transient failures (timeouts, transport errors, 429/5xx).

    Free ngrok/Colab tunnels stall or rate-limit under the sustained burst of a
    full-corpus ingest, so one bad batch must not abort the whole multi-minute run.
    """
    last: Exception | None = None
    for n in range(attempts):
        try:
            r = httpx.post(url, headers=headers, json=json, timeout=timeout)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = httpx.HTTPStatusError(f"transient {r.status_code}", request=r.request, response=r)
            else:
                r.raise_for_status()
                return r
        if n < attempts - 1:
            time.sleep(2.0 * (2**n))
    assert last is not None
    raise last


async def _apost_with_retry(
    client: httpx.AsyncClient, url: str, *, headers: dict, json: dict, attempts: int = 4
) -> httpx.Response:
    """Async twin of `_post_with_retry`, for the single-query serving path."""
    last: Exception | None = None
    for n in range(attempts):
        try:
            r = await client.post(url, headers=headers, json=json)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = httpx.HTTPStatusError(f"transient {r.status_code}", request=r.request, response=r)
            else:
                r.raise_for_status()
                return r
        if n < attempts - 1:
            await anyio.sleep(2.0 * (2**n))
    assert last is not None
    raise last


class CohereEmbedder:
    def __init__(self, s: Settings):
        self.name = s.embedding_model
        self.dim = 1024
        self._key = s.embedding_api_key
        self._url = (s.embedding_base_url or "https://api.cohere.com") + "/v2/embed"
        self._model = s.embedding_model
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _call(self, texts: list[str], input_type: str) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 96):
            r = _post_with_retry(
                self._url,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self._model,
                    "texts": texts[i : i + 96],
                    "input_type": input_type,
                    "embedding_types": ["float"],
                },
            )
            out += r.json()["embeddings"]["float"]
        return _l2(np.asarray(out, dtype=np.float32))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._call(texts, "search_document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._call([text], "search_query")[0]

    async def aembed_query(self, text: str) -> np.ndarray:
        r = await _apost_with_retry(
            self._get_client(),
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "texts": [text],
                "input_type": "search_query",
                "embedding_types": ["float"],
            },
        )
        return _l2(np.asarray(r.json()["embeddings"]["float"], dtype=np.float32))[0]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenAIEmbedder:
    def __init__(self, s: Settings):
        self.name = s.embedding_model
        self.dim = s.embedding_dim
        self._key = s.embedding_api_key
        self._url = (s.embedding_base_url or "https://api.openai.com/v1") + "/embeddings"
        self._model = s.embedding_model
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _call(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            r = _post_with_retry(
                self._url,
                headers={"Authorization": f"Bearer {self._key}"},
                json={"model": self._model, "input": texts[i : i + 128]},
            )
            out += [d["embedding"] for d in r.json()["data"]]
        arr = _l2(np.asarray(out, dtype=np.float32))
        self.dim = arr.shape[1]
        return arr

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._call(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._call([text])[0]

    async def aembed_query(self, text: str) -> np.ndarray:
        r = await _apost_with_retry(
            self._get_client(),
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": [text]},
        )
        arr = _l2(np.asarray([d["embedding"] for d in r.json()["data"]], dtype=np.float32))
        self.dim = arr.shape[1]
        return arr[0]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class SentenceTransformerEmbedder:
    def __init__(self, s: Settings):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self._m = SentenceTransformer(s.embedding_model)
        self.name = s.embedding_model
        self.dim = int(self._m.get_sentence_embedding_dimension())
        self._e5 = "e5" in s.embedding_model.lower()

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        texts = [f"passage: {t}" for t in texts] if self._e5 else texts
        return _l2(self._m.encode(texts, batch_size=32, show_progress_bar=False))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2(self._m.encode([f"query: {text}" if self._e5 else text]))[0]

    async def aembed_query(self, text: str) -> np.ndarray:
        # The model runs on CPU/GPU synchronously; keep it off the event loop.
        return await anyio.to_thread.run_sync(self.embed_query, text)


def get_embedder(s: Settings) -> Embedder:
    p = s.embedding_provider.lower()
    if p == "hashing":
        return HashingEmbedder(s.embedding_dim)
    if p == "cohere":
        return CohereEmbedder(s)
    if p == "openai":
        return OpenAIEmbedder(s)
    if p in ("sentence-transformers", "st"):
        return SentenceTransformerEmbedder(s)
    raise ValueError(f"unknown embedding provider: {s.embedding_provider}")
