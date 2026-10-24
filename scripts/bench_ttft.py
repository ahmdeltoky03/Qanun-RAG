"""Ad-hoc TTFT benchmark across Cohere chat models on a REALISTIC prompt.

Loads 4 real full-length articles from the corpus as context (no retrieval, so no
Qdrant lock contention with the running API) and measures time-to-first-visible-token
per model. command-a-plus does hidden reasoning that scales with question difficulty,
so a trivial prompt badly understates its real TTFT -- hence real article text here.
"""

import json
import time

import httpx

from qanun.config import get_settings
from qanun.llm import SYSTEM_AR

s = get_settings()
KEY = s.llm_api_key
URL = "https://api.cohere.com/compatibility/v1/chat/completions"

arts = json.load(open("data/processed/civil_code.json", encoding="utf-8"))
hits = [a for a in arts if "التعويض" in (a.get("text_ar") or "")][:4]
ctx = "\n\n".join(f"[المادة {a['article_number']}]\n{a['text_ar']}" for a in hits)
QUESTION = "ما حكم التعويض عن الضرر؟"
MSGS = [
    {"role": "system", "content": SYSTEM_AR},
    {"role": "user", "content": f"السياق:\n{ctx}\n\nالسؤال: {QUESTION}"},
]
print(f"context chars={len(ctx)} articles={[a['article_number'] for a in hits]}")


def bench(model, runs=2):
    ttfts = []
    lens = []
    for _ in range(runs):
        body = {"model": model, "temperature": 0.0, "max_tokens": 2048, "messages": MSGS, "stream": True}
        t0 = time.perf_counter()
        ttft = None
        ntok = 0
        try:
            with httpx.Client(timeout=180.0) as c:
                with c.stream("POST", URL, headers={"Authorization": f"Bearer {KEY}"}, json=body) as r:
                    if r.status_code != 200:
                        r.read()
                        return f"{model}: HTTP {r.status_code} {r.text[:120]}"
                    for line in r.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        d = line[5:].strip()
                        if d == "[DONE]":
                            break
                        try:
                            delta = json.loads(d)["choices"][0]["delta"].get("content")
                        except Exception:
                            delta = None
                        if delta:
                            if ttft is None:
                                ttft = time.perf_counter() - t0
                            ntok += 1
            total = time.perf_counter() - t0
            ttfts.append(ttft if ttft is not None else total)
            lens.append(ntok)
        except Exception as e:
            return f"{model}: ERR {e}"
    avg = sum(ttfts) / len(ttfts)
    return f"{model}: TTFT avg {avg:.2f}s  runs={[round(x,2) for x in ttfts]}  out_tokens~{lens}"


if __name__ == "__main__":
    for m in ["command-a-plus-05-2026", "command-a-03-2025", "command-r-plus-08-2024"]:
        print(bench(m))
