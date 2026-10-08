# ⚖️ القانون المدني المصري — Egyptian Civil Code Q&A

[![CI](https://github.com/YOUR/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR/REPO/actions)
[![Deploy](https://github.com/YOUR/REPO/actions/workflows/deploy.yml/badge.svg)](https://github.com/YOUR/REPO/actions)

A **production-style RAG service** that answers questions about the **Egyptian Civil Code** (1149 articles, Arabic + English) and **cites article numbers**. Refuses out-of-scope questions, blocks prompt injection, and masks personal data.

> العربية: [README.ar.md](README.ar.md)

```
PDF ──► corpus (1 JSON record / article) ──► chunks ──► embeddings ──► Qdrant index
                                                                            │
question ─► guardrails ─► hybrid retrieval (dense + BM25 + RRF) ─► LLM ─► citation check ─► {answer, sources}
```

---

## 📁 Project Structure

```
RAGGuide_/
├── src/                        ← Installable package (import prodml)
│   └── prodml/
│       ├── api/                ← FastAPI: main.py, schemas.py
│       ├── corpus/             ← PDF → JSON pipeline
│       ├── eval/               ← Evaluation runner + experiments
│       ├── config.py           ← Pydantic Settings (PRODML_* env vars)
│       ├── embeddings.py       ← bge-m3 / hashing / cohere / sentence-transformers
│       ├── retrieval.py        ← Dense + BM25 + RRF + cross-encoder
│       ├── rag.py              ← Main RAG pipeline
│       ├── llm.py              ← OpenAI-compatible LLM client
│       ├── guardrails.py       ← Prompt injection + PII masking
│       └── observability.py   ← Prometheus + Langfuse
│
├── tests/                      ← pytest (48 tests) — CI-ready from day 1
├── configs/
│   └── config.yaml             ← Central YAML config (no magic constants)
├── notebooks/
│   └── ollama_colab_ngrok.ipynb ← Run Ollama on Colab + ngrok tunnel
├── frontend/                   ← Next.js 14 UI (Arabic RTL, dark mode)
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── package.json
│   ├── vercel.json
│   └── next.config.js
├── docker/                     ← Dockerfile
├── docker-compose.yml          ← API + nginx + Prometheus + Grafana + Langfuse
├── deploy/                     ← nginx canary config
├── monitoring/                 ← Prometheus rules + Grafana dashboard
├── data/
│   ├── raw/                    ← Source PDF
│   ├── processed/              ← civil_code.json (1149 articles)
│   └── eval/                   ← 58-question eval set
├── reports/                    ← Evaluation outputs
├── loadtest/                   ← Locust load test
├── optimization/               ← AWQ + re-ranker distillation
├── scripts/
│   ├── canary.sh
│   └── git-setup.ps1           ← One-shot Git init + branches
├── railway.toml                ← Railway.app deployment config
├── pyproject.toml              ← Single source of truth for deps + tools
├── Makefile                    ← All dev commands
├── PROJECT_PROGRESS.json       ← Machine-readable progress tracker
└── PROJECT_PROGRESS.md         ← Human-readable progress tracker
```

---

## 🚀 Quick Start (2 minutes, fully offline)

### Option 1 — pip

```powershell
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install everything
pip install -e ".[dev,ui]"

# 3. Build corpus (PDF → JSON)
prodml-build-corpus

# 4. Build vector index
prodml-ingest

# 5. Start API server
uvicorn prodml.api.main:get_app --factory --port 8000
```

### Option 2 — uv (faster, reproducible)

```powershell
# Install uv
pip install uv

# Sync exact versions from uv.lock
uv sync --extra dev --extra ui

# Activate
.venv\Scripts\Activate.ps1

# Then use the same commands above or prefix with: uv run
uv run prodml-build-corpus
uv run prodml-ingest
uv run uvicorn prodml.api.main:get_app --factory --port 8000
```

### Test the API

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/ask" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "What does Article 147 say?"}' | Select-Object -ExpandProperty Content
```

```bash
# curl (WSL / Git Bash)
curl -s -X POST http://localhost:8000/ask \
  -H "content-type: application/json" \
  -d '{"question": "ماذا تقول المادة 147؟"}'
```

---

## 🤖 Use Real Models: Ollama on Colab + ngrok

> **Best setup:** Run the Colab notebook, paste the ngrok URL into `.env`, re-run `prodml-ingest`.

### Step 1 — Run the Colab Notebook

Open [`notebooks/ollama_colab_ngrok.ipynb`](notebooks/ollama_colab_ngrok.ipynb) in Google Colab:

1. Enable **GPU** (Runtime → Change runtime type → T4)
2. Add your `NGROK_AUTH_TOKEN` to Colab Secrets 🔑
3. Run all cells — the last cell prints your `.env` lines

### Step 2 — Update `.env`

```ini
# .env  (copy from .env.example, never commit)

PRODML_EMBEDDING_PROVIDER=openai
PRODML_EMBEDDING_BASE_URL=https://YOUR-NGROK-URL.ngrok-free.app/v1
PRODML_EMBEDDING_MODEL=bge-m3
PRODML_EMBEDDING_API_KEY=ollama

PRODML_LLM_PROVIDER=openai
PRODML_LLM_BASE_URL=https://YOUR-NGROK-URL.ngrok-free.app/v1
PRODML_LLM_MODEL=gpt-oss:20b
PRODML_LLM_API_KEY=ollama
```

### Step 3 — Re-build index + Run

```powershell
prodml-ingest          # rebuild with bge-m3 embeddings
uvicorn prodml.api.main:get_app --factory --port 8000
```

### Fallback (offline, no GPU needed)

```ini
PRODML_EMBEDDING_PROVIDER=hashing
PRODML_LLM_PROVIDER=fake
```

---

## 🎨 Next.js UI

A beautiful dark-mode Arabic-first chat interface.

### Install & Run

```powershell
# Requires Node.js 18+
# Download from: https://nodejs.org/

cd frontend
npm install
npm run dev      # → http://localhost:3000
```

### Build for Production

```powershell
cd frontend
npm run build
npm start
```

### Environment

```ini
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000       # local dev
# NEXT_PUBLIC_API_URL=https://YOUR-APP.railway.app   # production
```

---

## 🛠 All Make Commands

```powershell
make setup          # install Python package + dev tools
make corpus         # PDF → data/processed/civil_code.json
make index          # embed corpus → build Qdrant index
make run            # API on http://localhost:8000
make ui             # Streamlit UI on http://localhost:8501  (legacy)
make test           # pytest (48 tests)
make lint           # ruff check + format
make eval           # evaluate 58 questions → reports/latest_eval.json
make gate           # CI quality gate (fails if faithfulness < 0.75)
make experiments    # 12-run grid (chunk size / embedding / rerank)
make loadtest       # Locust 50 users (HOST=http://localhost:8000)
make up             # docker compose up --build -d
make down           # docker compose down
make canary PCT=10  # 10% to canary (0=rollback, 100=promote)
```

### Without `make` (Windows, direct commands)

```powershell
# Setup
pip install -e ".[dev,ui]"

# Corpus
prodml-build-corpus

# Index
prodml-ingest

# API
uvicorn prodml.api.main:get_app --factory --port 8000

# Tests
pytest

# Lint
ruff check src tests

# Eval
prodml-eval
prodml-eval --api http://localhost:8000 --out reports/latest_eval.json

# Quality gate
prodml-eval --sample 20 --gate --min-faithfulness 0.75
```

---

## 🐳 Docker (Full Stack)

```powershell
# Copy env
copy .env.example .env
# Edit .env with your model URLs

# Start everything
docker compose up --build -d
```

| URL | Service |
|-----|---------|
| `http://localhost:8080` | nginx → API |
| `http://localhost:9090` | Prometheus |
| `http://localhost:9093` | Alertmanager |
| `http://localhost:3001` | Grafana |

```powershell
# With Langfuse tracing
docker compose --profile tracing up -d

# Canary release
scripts\canary.sh 10    # 10% canary
scripts\canary.sh 0     # rollback
scripts\canary.sh 100   # promote
```

---

## 🌐 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST `{"question": "..."}` | Answer with sources |
| `/ask/stream` | POST | SSE streaming: `meta` → `token`s → `done` |
| `/health` | GET | `{status, documents_indexed, embedding_model, llm_model}` |
| `/metrics` | GET | Prometheus metrics |
| `/docs` | GET | Interactive Swagger UI |

---

## 🚢 Deploy (Free Tiers)

### API → Railway.app

```powershell
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Create project
railway new

# 4. Set environment variables in Railway dashboard:
#    PRODML_EMBEDDING_PROVIDER, PRODML_EMBEDDING_BASE_URL, etc.

# 5. Deploy
railway up
```

**Or link to GitHub:** Push to `main` → GitHub Actions auto-deploys via `RAILWAY_TOKEN` secret.

### UI → Vercel

```powershell
cd frontend

# 1. Install Vercel CLI
npm install -g vercel

# 2. Login
vercel login

# 3. Deploy (follow prompts)
vercel

# 4. Set env variable in Vercel dashboard:
#    NEXT_PUBLIC_API_URL = https://YOUR-APP.railway.app

# 5. Production deploy
vercel --prod
```

**Or import from GitHub:** vercel.com → New Project → Import repository → set env vars.

### Required GitHub Secrets

| Secret | Used By |
|--------|---------|
| `RAILWAY_TOKEN` | deploy.yml → Railway |
| `VERCEL_TOKEN` | deploy.yml → Vercel |
| `VERCEL_ORG_ID` | deploy.yml → Vercel |
| `VERCEL_PROJECT_ID` | deploy.yml → Vercel |
| `OPENAI_API_KEY` | ci.yml → quality gate (optional) |

---

## 🌿 Git Branch Strategy

```powershell
# One-shot setup (run after first clone)
.\scripts\git-setup.ps1 -Remote "https://github.com/YOUR/REPO.git"
```

| Branch | Purpose |
|--------|---------|
| `main` | Stable — only merges from PRs |
| `feat/project-structure` | Foundation + layouts |
| `feat/corpus-pipeline` | PDF → JSON → chunks |
| `feat/rag-engine` | Retrieval + LLM + guardrails |
| `feat/api-observability` | FastAPI + Prometheus + Langfuse |
| `feat/evaluation` | Eval set + quality gate |
| `feat/ollama-colab-ngrok` | Ollama server + ngrok notebook |
| `feat/nextjs-ui` | Next.js 14 frontend |
| `feat/deployment` | Railway + Vercel config |

```powershell
# Workflow per feature
git checkout feat/nextjs-ui
# ... make changes ...
git add -A
git commit -m "feat(ui): add streaming support"
git push origin feat/nextjs-ui
# Open PR → merge to main → auto-deploy
```

---

## 🧪 Tests & Evaluation

```powershell
pytest                          # 48 tests
pytest -m "not slow"            # skip PDF tests
pytest --cov=prodml             # with coverage

# Evaluate while API is running (avoids index lock)
prodml-eval --api http://localhost:8000 --out reports/latest_eval.json

# Full eval modes
prodml-eval --mode offline      # faithfulness proxy (default)
prodml-eval --mode ragas        # LLM judge (needs OPENAI_API_KEY)
```

---

## 📊 Project Progress

See [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md) for current status of all phases and branches.

---

## ⚠️ Known Limits

- Offline mode is weak (see above) — use real models for real answers
- Article 1022 has no Arabic text in the source PDF (known source defect)
- General information only — **not legal advice**
- Docker, Grafana, vLLM, AWQ not verified end-to-end (see [reports/STATUS.md](reports/STATUS.md))

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `RuntimeError: index folder in use` | Stop the server; or use `prodml-eval --api URL` |
| `/health` shows `degraded`, `documents_indexed: 0` | Run `prodml-ingest` |
| All answers are refusals after switching model | Re-run `prodml-ingest`; lower `PRODML_MIN_SCORE` |
| `vector dimension` error | Index built with different embedding model — re-run `prodml-ingest` |
| ngrok URL not working | Check Colab is still running; get a new tunnel URL |
| `npm: not recognized` | Install Node.js from https://nodejs.org/ |
