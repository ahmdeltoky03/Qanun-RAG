"""Offline evaluation metrics that need no LLM judge.

These are *proxies* for the RAGAS metrics (RAGAS itself needs a judge LLM). They are
deterministic, free, and good enough to catch regressions in CI; the RAGAS run is the
authoritative number and is reported separately (see `qanun.eval.run --mode ragas`).
"""

from __future__ import annotations

import re

from qanun.guardrails import cited_articles
from qanun.llm import NOT_FOUND_AR, NOT_FOUND_EN
from qanun.retrieval import tokens

_CITE_STRIP = re.compile(r"\[(?:المادة|Article)\s*\d+\]")


def is_refusal(answer: str) -> bool:
    return answer.strip() in (NOT_FOUND_AR, NOT_FOUND_EN)


def faithfulness_proxy(answer: str, contexts: list[str]) -> float:
    """Share of the answer's content words that appear in the retrieved context (1.0 = fully supported)."""
    ans = set(tokens(_CITE_STRIP.sub(" ", answer)))
    if not ans:
        return 1.0
    ctx = set(tokens(" ".join(contexts)))
    return len(ans & ctx) / len(ans)


def token_f1(pred: str, ref: str) -> float:
    p, r = tokens(_CITE_STRIP.sub(" ", pred)), tokens(ref)
    if not p or not r:
        return 0.0
    common = len(set(p) & set(r))
    if not common:
        return 0.0
    prec, rec = common / len(set(p)), common / len(set(r))
    return 2 * prec * rec / (prec + rec)


def retrieval_metrics(expected: list[int], retrieved: list[int]) -> dict[str, float]:
    if not expected:
        return {}
    ranks = [retrieved.index(e) + 1 for e in expected if e in retrieved]
    return {
        "hit_at_1": float(bool(retrieved) and retrieved[0] in expected),
        "hit_at_k": float(bool(ranks)),
        "mrr": 1.0 / min(ranks) if ranks else 0.0,
        "context_recall": len(ranks) / len(expected),
        "context_precision": sum(r in expected for r in retrieved) / max(len(retrieved), 1),
    }


def citation_accuracy(answer: str, expected: list[int]) -> float:
    cited = set(cited_articles(answer))
    return float(bool(cited & set(expected))) if expected else 1.0


def mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0
