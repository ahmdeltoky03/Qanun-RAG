# Status (what is proven, what is not)

## Verified by running it
| Area | Evidence |
|---|---|
| Corpus extraction | 1149 articles; repealed 54-80 and 389-417 flagged; rebuild is byte-identical; `tests/test_corpus.py` |
| API | `/ask` `/ask/stream` `/health` `/metrics`; 422 on empty input; sources are article numbers |
| Guardrails | injection blocked, PII removed, ungrounded citations dropped (`tests/test_chunking_guardrails.py`) |
| Tests / lint | 47 tests pass, ruff clean |
| Packaging | clean venv, non-editable `pip install .`, index build, server answers (replays the Dockerfile steps) |
| Load | 50 users, 45 s, single worker, offline stack: 0 failures, /ask p50 570 ms, p95 1500 ms, ~18 req/s (`reports/locust_stats.csv`) |
| Alert rules | `promtool check` + `promtool test rules`: FaithfulnessLow fires at 0.72 and not at 0.91; QueryDrift, EmptyIndex fire correctly |
| Canary (real nginx 1.24 + 2 API instances) | weight 0/10/50/100 -> 0/24/105/200 of 200 to canary; `X-Canary: always/never` override works; SSE passes through |
| Tracing | Langfuse call pattern + outage tolerance, against a fake SDK |
| Quality gate | separates a faithful generator (>=0.75) from a hallucinating one (<0.75); CLI exits 1 on failure |
| Dockerfile | hadolint clean |

Bugs found *by* these checks and fixed: reversed Arabic ligatures, hamza dropped by NFKD, labels swallowed into article text, a 3 s p50 under load (per-call Qdrant scans), nginx rejecting `0%` (would have broken rollback), a gate test that could not fail.

## Written but NOT run (no Docker / GPU / API keys / network to model hubs here)
`docker build` and `docker compose up`, Grafana dashboard rendering, a real Langfuse server, vLLM, AWQ quantisation, re-ranker distillation, real RAGAS, Cohere/OpenAI/sentence-transformers embeddings, GitHub Actions itself.

## Known limits
- Offline hashing embedder: hit@1 0.59, hit@4 0.76, out-of-scope accuracy 0.5 (it refuses pizza and the World Cup, but answers criminal-law and company-registration questions). A multilingual embedder should do much better; it is **not measured**.
- Offline faithfulness (~0.96) is a proxy over an extractive fake LLM. It is a regression smoke test, **not** a quality number. The authoritative number needs `--mode ragas` with a real generator.
- Article 1022 has no Arabic text in the source PDF (documented in the extraction report, not invented).
- Embedded Qdrant is single-process: one uvicorn worker per container, scale with replicas.

## You still need to do
1. Put real keys in `.env` and run `prodml-eval --mode ragas` (fill the table in `reports/module-3-5.md`).
2. `docker compose up --build`, then `scripts/canary.sh 10`.
3. Run `optimization/*` on a GPU/Colab and fill the before/after table.
4. Split the work into PRs per module and tag v0.1.0-v0.5.0.
5. Purge personal PDFs from the *remote* git history: `git filter-repo --path src/assets/files --invert-paths` (then force-push).
