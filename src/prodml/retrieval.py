"""Retrieval: explicit article lookup + dense search + lexical re-ranking."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from prodml.arabic import normalize_for_search
from prodml.config import Settings
from prodml.embeddings import Embedder
from prodml.vectorstore import VectorStore

_ARTICLE_REF = re.compile(
    r"(?:ماده|الماده|المواد|article|articles|art\.?)\s*(?:رقم|no\.?|#)?\s*[:\-]?\s*(\d{1,4})", re.I
)
_STOP = set(
    "في من على الى عن ما هل هو هي هذا هذه ذلك التي الذي ان او و ثم قد كل لا لم لن اذا كان يكون ماذا كيف متي اين "
    "the of and or to in is are a an for on by with what when how does do can may be it its that this which if".split()
)  # fmt: skip


@dataclass
class Retrieved:
    article_number: int
    score: float
    citation: str
    text_ar: str = ""
    text_en: str = ""
    chapter: str = ""
    section: str = ""
    is_repealed: bool = False
    source_page: int = 0
    explicit: bool = False
    pieces: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    items: list[Retrieved]
    top_vector_score: float
    out_of_scope: bool
    query_vector: list[float] | None = None
    coverage: float = 0.0


def tokens(text: str) -> list[str]:
    from prodml.arabic import light_stem

    return [light_stem(t) for t in re.findall(r"\w+", normalize_for_search(text)) if t not in _STOP and len(t) > 1]


def referenced_articles(question: str) -> list[int]:
    q = normalize_for_search(question)
    return list(dict.fromkeys(int(m.group(1)) for m in _ARTICLE_REF.finditer(q)))[:3]


class LexicalIndex:
    """In-memory BM25 over chunk texts (2-3k chunks: trivial to hold and instant to build)."""

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [(c["article_number"], c["is_repealed"], tokens(c["text"])) for c in chunks]
        self.n = len(self.docs)
        self.avg = sum(len(t) for _, _, t in self.docs) / max(self.n, 1)
        self.df: dict[str, int] = {}
        for _, _, toks in self.docs:
            for t in set(toks):
                self.df[t] = self.df.get(t, 0) + 1
        self.tf = [{t: toks.count(t) for t in set(toks)} for _, _, toks in self.docs]

    def idf(self, term: str) -> float:
        d = self.df.get(term, 0)
        return math.log(1 + (self.n - d + 0.5) / (d + 0.5))

    def search(self, query_tokens: list[str], include_repealed: bool = False) -> dict[int, tuple[float, float]]:
        """article -> (bm25, idf-weighted coverage of query terms by the best chunk)."""
        qt = list(dict.fromkeys(query_tokens))
        total_idf = sum(self.idf(t) for t in qt) or 1.0
        best: dict[int, tuple[float, float]] = {}
        for (num, rep, toks), tf in zip(self.docs, self.tf, strict=True):
            if rep and not include_repealed:
                continue
            score = cov = 0.0
            for t in qt:
                f = tf.get(t)
                if f:
                    idf = self.idf(t)
                    score += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(toks) / self.avg))
                    cov += idf
            if score > 0 and score > best.get(num, (0.0, 0.0))[0]:
                best[num] = (score, cov / total_idf)
        return best


def rrf(rankings: list[list[int]], k: int = 30, weights: list[float] | None = None) -> dict[int, float]:
    weights = weights or [1.0] * len(rankings)
    out: dict[int, float] = {}
    for w, ranking in zip(weights, rankings, strict=True):
        for rank, n in enumerate(ranking):
            out[n] = out.get(n, 0.0) + w / (k + rank + 1)
    return out


class Retriever:
    def __init__(self, s: Settings, store: VectorStore, embedder: Embedder):
        self.s, self.store, self.embedder = s, store, embedder
        self._cross = None
        self._lex: LexicalIndex | None = None
        self._articles: dict[int, list[dict]] = {}

    def _cross_encoder(self):
        if self._cross is None:
            from sentence_transformers import CrossEncoder  # optional dependency

            self._cross = CrossEncoder(self.s.cross_encoder_model)
        return self._cross

    def _article_rows(self, number: int) -> list[dict]:
        """All chunks of one article, served from memory (a local Qdrant scroll costs ~25 ms per call)."""
        self._lexical()
        return self._articles.get(number, [])

    def _hydrate(self, number: int, score: float, explicit: bool = False) -> Retrieved | None:
        rows = self._article_rows(number)
        if not rows:
            return None
        ar = sorted((r for r in rows if r["lang"] == "ar"), key=lambda r: r["piece"])
        en = sorted((r for r in rows if r["lang"] == "en"), key=lambda r: r["piece"])
        base = (ar or en)[0]
        return Retrieved(
            article_number=number, score=score, citation=base["citation"],
            text_ar="\n".join(r["text"] for r in ar), text_en=" ".join(r["text"] for r in en),
            chapter=base.get("chapter", ""), section=base.get("section", ""),
            is_repealed=base["is_repealed"], source_page=base["source_page"], explicit=explicit,
        )  # fmt: skip

    def _lexical(self) -> LexicalIndex:
        if self._lex is None:
            chunks = self.store.all_chunks()
            for c in chunks:
                self._articles.setdefault(c["article_number"], []).append(c)
            self._lex = LexicalIndex(chunks)
        return self._lex

    def search(self, question: str, top_k: int | None = None) -> RetrievalResult:
        """Hybrid retrieval: dense + BM25 fused with RRF, optional cross-encoder, explicit article lookup."""
        top_k = top_k or self.s.top_k
        qvec = self.embedder.embed_query(normalize_for_search(question))
        hits = self.store.search(qvec, limit=self.s.candidate_k * 2)
        dense: dict[int, float] = {}
        for h in hits:
            dense[h["article_number"]] = max(dense.get(h["article_number"], 0.0), h["score"])
        top_vec = max(dense.values(), default=0.0)
        dense_rank = sorted(dense, key=dense.get, reverse=True)

        coverage = 0.0
        if self.s.rerank == "none":
            fused = {n: dense[n] for n in dense_rank}
        else:
            lex = self._lexical().search(tokens(question))
            lex_rank = sorted(lex, key=lambda n: lex[n][0], reverse=True)[: self.s.candidate_k * 2]
            fused = rrf([dense_rank, lex_rank], weights=[self.s.dense_weight, 1.0 - self.s.dense_weight])
            coverage = max((lex[n][1] for n in lex_rank[:5]), default=0.0)
        cand = sorted(fused, key=fused.get, reverse=True)[: self.s.candidate_k]
        scored = dict(fused)

        if self.s.rerank == "cross-encoder" and cand:
            pairs = []
            for n in cand:
                rows = self._article_rows(n)
                pairs.append((question, " ".join(r["text"] for r in rows)))
            for n, sc in zip(cand, self._cross_encoder().predict(pairs), strict=True):
                scored[n] = float(sc)
            cand.sort(key=scored.get, reverse=True)

        items: list[Retrieved] = []
        for n in referenced_articles(question):  # "what does article 147 say?" -> go straight to it
            r = self._hydrate(n, 1.0, explicit=True)
            if r:
                items.append(r)
        for n in [] if items else cand:  # an explicit "Article N" question is answered from that article alone
            if len(items) >= top_k:
                break
            if any(i.article_number == n for i in items):
                continue
            r = self._hydrate(n, scored[n])
            if r:
                items.append(r)
        explicit = any(i.explicit for i in items)
        if self.s.rerank == "none":
            relevant = top_vec >= self.s.min_score
        else:
            relevant = coverage >= self.s.min_coverage and top_vec >= self.s.min_score
        return RetrievalResult(
            items[:top_k],
            top_vec,
            out_of_scope=(not relevant and not explicit),
            query_vector=qvec.tolist(),
            coverage=coverage,
        )
