"""Build the vector index from the structured corpus (run at Docker build time)."""

from __future__ import annotations

import argparse
import json
import logging
import time

import numpy as np

from qanun.chunking import build_chunks
from qanun.config import Settings, get_settings
from qanun.embeddings import get_embedder
from qanun.vectorstore import VectorStore

log = logging.getLogger(__name__)


def build_index(s: Settings) -> dict:
    t0 = time.perf_counter()
    records = json.loads(s.corpus_path.read_text(encoding="utf-8"))
    chunks = build_chunks(records, s.chunk_size, s.chunk_overlap)
    embedder = get_embedder(s)
    vectors = embedder.embed_documents([c.embed_text for c in chunks])
    store = VectorStore(s)
    store.recreate(vectors.shape[1])
    store.upsert(chunks, vectors)
    stats = {
        "articles": len(records),
        "chunks": len(chunks),
        "embedding": embedder.name,
        "dim": int(vectors.shape[1]),
        "chunk_size": s.chunk_size,
        "seconds": round(time.perf_counter() - t0, 2),
    }
    log.info("indexed %s", stats)
    return stats


def save_query_baseline(s: Settings, questions_path: str = "data/eval/questions.json") -> None:
    """Embed the evaluation questions once; their centroid is the drift baseline."""
    from qanun.arabic import normalize_for_search
    from qanun.drift import save_baseline

    try:
        qs = json.loads(open(questions_path, encoding="utf-8").read())
    except OSError:
        return
    emb = get_embedder(s)
    vecs = np.stack([emb.embed_query(normalize_for_search(q["question"])) for q in qs])
    save_baseline(vecs, s.drift_baseline_path, emb.name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", default="data/eval/questions.json")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = get_settings()
    print(json.dumps(build_index(s), ensure_ascii=False))
    save_query_baseline(s, args.questions)


if __name__ == "__main__":
    main()
