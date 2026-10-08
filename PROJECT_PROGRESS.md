# 📊 Project Progress

> Auto-generated from `PROJECT_PROGRESS.json` — last updated: 2026-10-08

## Overview

| Phase | Branch | Status |
|-------|--------|--------|
| 1. Project Foundation & Structure | `feat/project-structure` | ✅ Done |
| 2. Corpus Pipeline | `feat/corpus-pipeline` | ✅ Done |
| 3. RAG Core Engine | `feat/rag-engine` | ✅ Done |
| 4. API & Observability | `feat/api-observability` | ✅ Done |
| 5. Evaluation & Quality Gate | `feat/evaluation` | ✅ Done |
| 6. Ollama + ngrok | `feat/ollama-ngrok` | 🔄 In Progress |
| 7. Next.js UI | `feat/nextjs-ui` | 🔄 In Progress |
| 8. Production Deployment | `feat/deployment` | ⏳ Todo |

## Current Focus: Phase 6 — Ollama + ngrok

- [x] Ollama models chosen: `gpt-oss:20b` (LLM) + `bge-m3` (embedding)
- [x] Env vars wired to an ngrok tunnel URL in `.env` / `.env.example`
- [ ] ngrok tunnel → live public URL (free URLs change on each restart)
- [ ] Re-run `qanun-ingest` against the live tunnel to rebuild the bge-m3 index
- [ ] End-to-end test

> The Colab notebook is not part of the repo. Ollama runs on a Colab GPU on port
> 8000 (`OLLAMA_HOST=0.0.0.0:8000`) and is tunneled with pyngrok
> (`ngrok.connect("8000")`); any OpenAI-compatible endpoint works.

## Branch Strategy

> Reality check: the repo currently has a **single commit** (`f1bdf09`) and all
> feature branches point at it — no PRs have been opened or merged yet. The
> branches below are the intended layout created by `scripts/git-setup.ps1`;
> move each phase's work onto its branch and merge via PR as you go.

```
main                ← stable, only PRs merged here
  ├── feat/project-structure    (not yet merged)
  ├── feat/corpus-pipeline      (not yet merged)
  ├── feat/rag-engine           (not yet merged)
  ├── feat/api-observability    (not yet merged)
  ├── feat/evaluation           (not yet merged)
  ├── feat/ollama-ngrok         (current focus)
  ├── feat/nextjs-ui            (open)
  └── feat/deployment           (next)
```

## Models

| Role | Model | Provider |
|------|-------|----------|
| LLM | `gpt-oss:20b` | Ollama (via ngrok tunnel) |
| Embedding | `bge-m3` | Ollama (via ngrok tunnel) |
| LLM fallback | `fake` (extractive) | offline |
| Embedding fallback | `hashing` | offline |

## Deployment Targets

| Component | Platform | URL |
|-----------|----------|-----|
| FastAPI | Railway.app (free) | `https://qanun.railway.app` |
| Next.js UI | Vercel (free) | `https://qanun.vercel.app` |
| Monitoring | Docker Compose | local |
