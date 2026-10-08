"""Thin Qdrant wrapper. Local on-disk mode by default, so the index ships inside the image."""

from __future__ import annotations

import numpy as np
from qdrant_client import QdrantClient, models

from qanun.chunking import Chunk
from qanun.config import Settings


class VectorStore:
    def __init__(self, s: Settings):
        self.collection = s.collection
        if s.qdrant_url:
            self.client = QdrantClient(url=s.qdrant_url)
        else:
            s.index_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.client = QdrantClient(path=str(s.index_dir / "qdrant"))
            except RuntimeError as e:  # embedded Qdrant allows one process per folder
                raise RuntimeError(
                    f"The index folder {s.index_dir} is in use by another process (is the API server running?). "
                    "Stop it first, or evaluate the running server with `qanun-eval --api http://localhost:8000`, "
                    "or set QANUN_QDRANT_URL to use a Qdrant server."
                ) from e

    def recreate(self, dim: int) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE)
        )

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray, batch: int = 128) -> None:
        for i in range(0, len(chunks), batch):
            self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(id=c.id, vector=v.tolist(), payload=c.payload)
                    for c, v in zip(chunks[i : i + batch], vectors[i : i + batch], strict=True)
                ],
            )

    def count(self) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, exact=True).count

    def distinct_articles(self) -> int:
        """Number of distinct articles indexed (what /health reports as documents_indexed)."""
        if not self.client.collection_exists(self.collection):
            return 0
        seen: set[int] = set()
        offset = None
        while True:
            pts, offset = self.client.scroll(self.collection, limit=512, offset=offset, with_payload=["article_number"])
            seen.update(p.payload["article_number"] for p in pts)
            if offset is None:
                return len(seen)

    def search(
        self, vector: np.ndarray, limit: int, lang: str | None = None, include_repealed: bool = False
    ) -> list[dict]:
        must: list[models.Condition] = []
        if lang:
            must.append(models.FieldCondition(key="lang", match=models.MatchValue(value=lang)))
        if not include_repealed:
            must.append(models.FieldCondition(key="is_repealed", match=models.MatchValue(value=False)))
        res = self.client.query_points(
            self.collection,
            query=vector.tolist(),
            limit=limit,
            query_filter=models.Filter(must=must) if must else None,
            with_payload=True,
        )
        return [{"score": float(p.score), **p.payload} for p in res.points]

    def all_chunks(self) -> list[dict]:
        out: list[dict] = []
        offset = None
        while True:
            pts, offset = self.client.scroll(self.collection, limit=512, offset=offset, with_payload=True)
            out += [dict(p.payload) for p in pts]
            if offset is None:
                return out

    def get_article(self, number: int) -> list[dict]:
        pts, _ = self.client.scroll(
            self.collection,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="article_number", match=models.MatchValue(value=number))]
            ),
            limit=8,
            with_payload=True,
        )
        return [dict(p.payload) for p in pts]
