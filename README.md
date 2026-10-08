# ⚖️ Qanun-RAG — Egyptian Civil Code Q&A (القانون المدني المصري)

[![CI](https://github.com/YOUR/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR/REPO/actions)
[![Deploy](https://github.com/YOUR/REPO/actions/workflows/deploy.yml/badge.svg)](https://github.com/YOUR/REPO/actions)

**Qanun-RAG** (قانون) is a **production-style RAG service** that answers questions about the **Egyptian Civil Code** (1149 articles, Arabic + English) and **cites article numbers**. Refuses out-of-scope questions, blocks prompt injection, and masks personal data.

> العربية: [README.ar.md](README.ar.md)

```
PDF ──► corpus (1 JSON record / article) ──► chunks ──► embeddings ──► Qdrant index
                                                                            │
question ─► guardrails ─► hybrid retrieval (dense + BM25 + RRF) ─► LLM ─► citation check ─► {answer, sources}
```

---

## 📁 Project Structure

```
Qanun-RAG/
├── src/                        ← Installable package (import qanun)
│   └── qanun/
│       ├── api/                ← FastAPI: main.py, schemas.py
│       ├── corpus/             ← PDF → JSON pipeline
│       ├── eval/               ← Evaluation runner + experiments
│       ├── config.py           ← Pydantic Settings (QANUN_* env vars)
│       ├── embeddings.py       ← bge-m3 / hashing / cohere / sentence-transformers
│       ├── retrieval.py        ← Dense + BM25 + RRF + cross-encoder
│       ├── rag.py              ← Main RAG pipeline
│       ├── llm.py              ← OpenAI-compatible LLM client
│       ├── guardrails.py       ← Prompt injection + PII masking
│       └── observability.py   ← Prometheus + Langfuse
│
├── tests/                      ← pytest (48 tests) — CI-ready from day 1
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
qanun-build-corpus

# 4. Build vector index
qanun-ingest

# 5. Start API server
uvicorn qanun.api.main:get_app --factory --port 8000
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
uv run qanun-build-corpus
uv run qanun-ingest
uv run uvicorn qanun.api.main:get_app --factory --port 8000
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

> **The workflow used here:** run Ollama on a **Colab GPU**, tunnel it with **ngrok**, paste the public URL into `.env`, re-run `qanun-ingest`. (Any OpenAI-compatible endpoint works — local Ollama, a LAN box, or cloud.)

### Step 1 — Colab: serve Ollama + open the tunnel

On Colab (GPU runtime), the notebook does:

```bash
# install Ollama
!curl -fsSL https://ollama.com/install.sh | sh

# serve on port 8000, allow cross-origin
!nohup bash -c "OLLAMA_HOST=0.0.0.0:8000 OLLAMA_ORIGIN=* ollama serve" &

# pull the models
!ollama pull gpt-oss:20b
!ollama pull bge-m3:latest
```

Then tunnel port **8000** with pyngrok (auth token from Colab Secrets):

```python
from google.colab import userdata
from pyngrok import ngrok, conf
conf.get_default().auth_token = userdata.get('colab-ngrok')
print(ngrok.connect("8000").public_url)   # → https://XXXX-...-....ngrok-free.app
```

> ⚠️ Free ngrok URLs **change every time the tunnel restarts** (and Colab sessions die). When you get a new URL, update `.env` and re-run `qanun-ingest`.

### Step 2 — Paste the URL into `.env` (on your machine)

Append `/v1` — that's Ollama's OpenAI-compatible base path:

```ini
# .env  (copy from .env.example, never commit)

QANUN_EMBEDDING_PROVIDER=openai
QANUN_EMBEDDING_BASE_URL=https://YOUR-TUNNEL.ngrok-free.app/v1
QANUN_EMBEDDING_MODEL=bge-m3
QANUN_EMBEDDING_API_KEY=ollama

QANUN_LLM_PROVIDER=openai
QANUN_LLM_BASE_URL=https://YOUR-TUNNEL.ngrok-free.app/v1
QANUN_LLM_MODEL=gpt-oss:20b
QANUN_LLM_API_KEY=ollama
```

### Step 3 — Re-build index + Run

```powershell
qanun-ingest          # rebuild with bge-m3 embeddings (needs the live tunnel)
uvicorn qanun.api.main:get_app --factory --port 8000
```

> Ollama listens on **Colab:8000** (behind ngrok); the FastAPI app listens on **your machine:8000**. Different machines — no port clash.

### Fallback (offline, no GPU / no tunnel)

```ini
QANUN_EMBEDDING_PROVIDER=hashing
QANUN_LLM_PROVIDER=fake
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
make ui             # Streamlit UI on http://localhost:8501
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
qanun-build-corpus

# Index
qanun-ingest

# API
uvicorn qanun.api.main:get_app --factory --port 8000

# Tests
pytest

# Lint
ruff check src tests

# Eval
qanun-eval
qanun-eval --api http://localhost:8000 --out reports/latest_eval.json

# Quality gate
qanun-eval --sample 20 --gate --min-faithfulness 0.75
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
#    QANUN_EMBEDDING_PROVIDER, QANUN_EMBEDDING_BASE_URL, etc.

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
| `feat/ollama-ngrok` | Ollama server + ngrok tunnel wiring |
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
pytest --cov=qanun             # with coverage

# Evaluate while API is running (avoids index lock)
qanun-eval --api http://localhost:8000 --out reports/latest_eval.json

# Full eval modes
qanun-eval --mode offline      # faithfulness proxy (default)
qanun-eval --mode ragas        # LLM judge (needs OPENAI_API_KEY)
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
| `RuntimeError: index folder in use` | Stop the server; or use `qanun-eval --api URL` |
| `/health` shows `degraded`, `documents_indexed: 0` | Run `qanun-ingest` |
| All answers are refusals after switching model | Re-run `qanun-ingest`; lower `QANUN_MIN_SCORE` |
| `vector dimension` error | Index built with different embedding model — re-run `qanun-ingest` |
| ngrok URL not working | Free tunnel URLs change on restart — re-run the Colab ngrok cell (`ngrok.connect("8000")`), copy the new URL into `.env`, re-run `qanun-ingest` |
| `npm: not recognized` | Install Node.js from https://nodejs.org/ |
