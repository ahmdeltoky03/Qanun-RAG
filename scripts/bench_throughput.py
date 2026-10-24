"""Generation-throughput benchmark across Cohere chat models (why is /ask slow?).

The /ask latency profile showed retrieve ~0.8s but generate ~8s: time-to-first-token is
fine, the cost is sustained generation. This measures, per model on a REALISTIC prompt:
  ttft_s      time to first visible token
  total_s     time to last token
  gen_s       total - ttft  (the streaming body the user waits through)
  tok_per_s   approx output throughput (SSE chunks / gen_s)
  answer      first ~140 chars + whether it carries a [المادة N] citation (faithfulness)

No retrieval here (no Qdrant lock contention with the running API).
"""

import json
import re
import sys
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
CITE = re.compile(r"\[(?:المادة|Article)\s*(\d{1,4})\]")


def bench(model: str) -> None:
    body = {"model": model, "temperature": 0.0, "max_tokens": 2048, "messages": MSGS, "stream": True}
    t0 = time.perf_counter()
    ttft = None
    chunks = 0
    text = []
    try:
        with httpx.Client(timeout=180.0) as c:
            with c.stream("POST", URL, headers={"Authorization": f"Bearer {KEY}"}, json=body) as r:
                if r.status_code != 200:
                    r.read()
                    print(f"{model}: HTTP {r.status_code} {r.text[:120]}")
                    return
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
                        chunks += 1
                        text.append(delta)
    except Exception as e:  # noqa: BLE001
        print(f"{model}: ERR {e}")
        return
    total = time.perf_counter() - t0
    ttft = ttft if ttft is not None else total
    gen = max(total - ttft, 1e-6)
    answer = "".join(text)
    cites = CITE.findall(answer)
    print(
        f"{model}:\n"
        f"   ttft={ttft:.2f}s  total={total:.2f}s  gen={gen:.2f}s  chunks={chunks}  ~{chunks/gen:.0f} tok/s\n"
        f"   cites={cites}  answer={answer[:140]!r}"
    )


if __name__ == "__main__":
    models = sys.argv[1:] or [
        "command-r-plus-08-2024",
        "command-r-08-2024",
        "command-r7b-12-2024",
    ]
    print(f"context chars={len(ctx)} articles={[a['article_number'] for a in hits]}\n")
    for m in models:
        bench(m)
