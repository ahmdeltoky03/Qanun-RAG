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
| 6. Ollama + Colab + ngrok | `feat/ollama-colab-ngrok` | 🔄 In Progress |
| 7. Next.js UI | `feat/nextjs-ui` | 🔄 In Progress |
| 8. Production Deployment | `feat/deployment` | ⏳ Todo |

## Current Focus: Phase 6 — Ollama + Colab + ngrok

- [x] Colab notebook: install Ollama + pull gpt-oss:20b + bge-m3
- [ ] ngrok tunnel → public URL
- [ ] Wire env vars to ngrok URL
- [ ] End-to-end test

## Branch Strategy

```
main                ← stable, only PRs merged here
  └── feat/project-structure   ✅ merged
  └── feat/corpus-pipeline     ✅ merged  
  └── feat/rag-engine          ✅ merged
  └── feat/api-observability   ✅ merged
  └── feat/evaluation          ✅ merged
  └── feat/ollama-colab-ngrok  🔄 current
  └── feat/nextjs-ui           🔄 open
  └── feat/deployment          ⏳ next
```

## Models

| Role | Model | Provider |
|------|-------|----------|
| LLM | `gpt-oss:20b` | Ollama (Colab + ngrok) |
| Embedding | `bge-m3` | Ollama (Colab + ngrok) |
| LLM fallback | `fake` (extractive) | offline |
| Embedding fallback | `hashing` | offline |

## Deployment Targets

| Component | Platform | URL |
|-----------|----------|-----|
| FastAPI | Railway.app (free) | `https://ragguide.railway.app` |
| Next.js UI | Vercel (free) | `https://ragguide.vercel.app` |
| Monitoring | Docker Compose | local |
