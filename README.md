# Qanun-RAG — Egyptian Civil Code Q&A

Qanun-RAG is my graduation project for the MLOps course: a production-style RAG service that answers questions about the Egyptian Civil Code (1149 articles, Arabic and English) and cites the article numbers it relied on. It refuses out-of-scope questions, blocks prompt-injection attempts, masks personal data, and every single answer is traceable end to end in Langfuse.

This README is written as my own runbook: exactly what I do on a fresh machine to bring the whole thing up, and every URL I keep open to check it and demo it. Follow it top to bottom and you will end up with the same setup I demonstrate.

العربية: [README.ar.md](README.ar.md)

## What you need before starting

- Python 3.10 or newer
- Node.js 18 or newer (for the Next.js UI)
- Docker Desktop, for Prometheus, Grafana, Alertmanager and Langfuse. The API itself does not need Docker at all.
- A Cohere API key. The free trial tier is enough, that is what I run on. Any OpenAI-compatible endpoint works instead, and there is a fully offline fallback if you have neither.
- Around half an hour of patience the first time: building the vector index paces itself under the Cohere trial rate cap.

## 1. Clone and install

```bash
git clone https://github.com/ahmdeltoky03/Qanun-RAG.git
cd Qanun-RAG
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Linux / WSL:         source .venv/bin/activate
pip install -e ".[dev,ui]"
```

I develop on Windows inside WSL; the commands are identical either way.

## 2. Configure .env

```bash
cp .env.example .env      # on Windows: copy .env.example .env
```

Open `.env` and paste your Cohere key in two places: `QANUN_EMBEDDING_API_KEY` and `QANUN_LLM_API_KEY` (the same key). The defaults already point embeddings at Cohere `embed-v5.0-pro` and the chat model at `command-r7b-12-2024` through Cohere's OpenAI-compatible endpoint, which is exactly my setup. `.env` is gitignored; never commit it.

Two knobs worth knowing:

- `QANUN_EMBEDDING_RPM=18` keeps the embedding client under the trial cap of 20 requests per minute. Leave it as is.
- `QANUN_CORS_ORIGINS` must contain `http://localhost:3000`, otherwise the browser UI cannot call the API.

No key at all? The bottom of `.env.example` has a fully offline fallback (hashing embeddings plus a fake LLM). Everything still boots and the tests still pass; answers are just placeholders.

## 3. Build the vector index

```bash
qanun-build-corpus    # PDF -> data/processed/civil_code.json (already in the repo, so normally you skip this)
qanun-ingest          # embed ~3450 chunks -> local Qdrant index under data/index
```

The corpus JSON is committed, so in practice you only run `qanun-ingest`. On the trial key it takes roughly 25 minutes because I pace the embedding calls to stay under the rate cap. You only rebuild when you change the embedding model.

Important: the embedded Qdrant index is locked by whichever process opened it. Never run `qanun-ingest` (or an offline eval) while the API server is running.

## 4. Start the API

```bash
make run
# identical to: uvicorn qanun.api.main:get_app --factory --host 0.0.0.0 --port 8000
```

I bind to 0.0.0.0 on purpose: the Prometheus container scrapes the API through the Docker host address, and a loopback-only bind is invisible from inside a container.

## 5. Start the UI

```bash
cd frontend
npm install
npm run dev
```

## 6. Start the observability stack

With Docker Desktop running:

```bash
docker compose --profile tracing up -d --no-deps langfuse-db langfuse prometheus grafana alertmanager
```

The `--no-deps` flag skips building the API Docker images: I run the API natively, and building those images would re-ingest the whole corpus through the rate cap for no benefit. On the very first boot Langfuse sometimes loses the start race against its postgres and exits; if `docker ps` shows it as exited, just run the same command again. The containers have no restart policy, so after a reboot I re-run this one command plus `make run`.

## Every URL I keep open

App and API, no Docker needed:

- http://localhost:3000 — the Next.js UI. Arabic-first RTL chat, tokens stream in live, and each answer card shows the latency, the source articles with their full text, and the Langfuse trace id.
- http://localhost:8000/docs — Swagger UI for the whole API, handy for trying endpoints by hand.
- http://localhost:8000/health — status, indexed article count, model names, tracing on or off.
- http://localhost:8000/metrics — the raw Prometheus metrics.
- http://localhost:8000/suggest?n=5 — random questions generated from the whole corpus; the suggestion chips in the UI come from here.

Dashboards and tracing, from the Docker stack:

- http://localhost:9090 — Prometheus, no login. Try `rate(rag_requests_total[2m])` or the `rag_stage_seconds` histograms.
- http://localhost:3001 — Grafana, login admin / admin (or your `GRAFANA_PASSWORD`). Open the RAG Overview dashboard: request rate, latency percentiles, cache hit rate, indexed documents, and a faithfulness gauge that reads `reports/latest_eval.json` on every scrape.
- http://localhost:9093 — Alertmanager. It fires when faithfulness drops below 0.80 or the error rate spikes.
- http://localhost:3100 — Langfuse, login admin@example.com / change-me-now, project `civil-code`. Every /ask and /ask/stream becomes a full trace. It lives on 3100 because 3000 belongs to the UI.

## How I demo tracing

I ask a question in the UI, copy the trace id printed at the bottom of the answer card, and search for it under Traces in Langfuse at http://localhost:3100/project/civil-code/traces. The trace shows the whole chain: guardrails, hybrid retrieval (dense plus BM25 fused with RRF), the Cohere generation, the citation check, and the faithfulness score attached afterwards. Even without an id, the trace list shows the latest requests with latency and token counts, which is what I open while a load test runs.

## Quality: eval and the CI gate

```bash
make eval     # all 58 questions -> reports/latest_eval.json (about 4 minutes)
make gate     # same run, but exits non-zero if faithfulness < 0.75
```

My latest full run: faithfulness 0.897, context recall 0.889, hit@k 0.889, MRR 0.776, citation accuracy 0.648, out-of-scope refusal 1.00, p50 latency 2.05 s. CI runs this gate on every pull request. If the API is running, use `qanun-eval --api http://localhost:8000` so the eval does not fight over the index lock.

## Load test

```bash
make loadtest     # 50 users for 2 minutes, headless Locust
# writes reports/locust.html and reports/locust_*.csv
```

The API caches answers in process, so I warm the cache first by running the eval set once against the live API (`qanun-eval --api http://localhost:8000`). That way the load test measures my serving path instead of Cohere's quota. My latest warm run: 4609 requests, zero failures, /ask p50 6 ms, p95 17 ms, p99 47 ms, around 42 requests per second aggregated.

## Tests and lint

```bash
make test     # 66 tests
make lint     # ruff check + format check
```

## Optional: the full stack in Docker

`make up` builds and runs everything containerized, including nginx with weighted canary routing on http://localhost:8080 (`scripts/canary.sh 10` sends 10 percent of traffic to the canary, 0 rolls back, 100 promotes). I only use this path for deploy drills: building the API image re-ingests the corpus through the rate cap, which is why my daily setup is the native API plus the Docker collectors above.

## Things that will bite you, because they all bit me

- "index folder in use": the API is running. Stop it before ingest or an offline eval.
- Langfuse exits on first boot: it lost the race against postgres. Re-run the compose command once.
- Dashboards dead after a reboot: no restart policy on the containers. Re-run the compose command and `make run`.
- UI shows Offline while curl to /health works: `http://localhost:3000` is missing from `QANUN_CORS_ORIGINS`.
- Nothing changes after editing .env: settings are read once at boot, restart the API.
- `vector dimension` error after switching embedding model: rebuild the index with `qanun-ingest`.
- Article 1022 has no Arabic text in the source PDF. That is a defect in the source document, not in the pipeline.

## Known limits

- Vague or out-of-scope questions get refused by design; that is the guardrails doing their job.
- The offline fallback exists for smoke tests and CI, not for answer quality.
- General information only, not legal advice.

## Repo map and branches

`src/qanun` is the installable package (api, corpus, retrieval, rag, llm, guardrails, eval, observability). `tests/` holds the pytest suite, `frontend/` the Next.js app, `monitoring/` the Prometheus rules and the Grafana dashboard, `loadtest/` the Locust profile, and `reports/` collects eval and load-test outputs.

`main` only takes merges from feature branches; my current development branch is `feat/cohere-provider`. The older `feat/*` branches each isolate one slice of the system (corpus pipeline, retrieval, API and observability, evaluation, UI, deployment) so each piece can be reviewed on its own.
