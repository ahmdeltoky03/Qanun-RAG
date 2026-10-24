# Deploying Qanun-RAG for free (public link)

This is the runbook I follow to put the whole app behind two public URLs I can
share with anyone — **$0/month**, no credit card. The API runs on Render's free
web service, the UI on Vercel's free (Hobby) tier. Both auto-deploy from this
GitHub repo on every push to `main`.

العربية: [DEPLOY.ar.md](DEPLOY.ar.md)

```
Render (free)                          Vercel (free)
  qanun-api  ◄── fetch /ask/stream ──── qanun-rag UI
  https://qanun-api.onrender.com        https://qanun-rag.vercel.app
```

## What "free" actually costs you (read this first)

The honest trade-offs of a $0 host, so the demo doesn't surprise you:

- **Cold start + one-time re-ingest.** Render's free instance sleeps after ~15
  minutes idle. The first request wakes it, and because the vector index
  (`data/index/`, 68 MB) is gitignored, the boot script rebuilds it from the
  committed corpus before serving — about **2 minutes**, paced under the Cohere
  trial rate cap. After that it's warm and fast until it sleeps again. This is
  the single biggest caveat of the free tier.
- **512 MB RAM.** The embedded Qdrant index plus the API fit, but there is no
  headroom for load. Fine for a handful of people trying it; not for a load test.
- **Cohere trial quota.** A public link means strangers spend your embedding /
  chat quota. The in-process answer cache absorbs repeats, and
  `QANUN_EMBEDDING_RPM=18` keeps ingest under the 20 req/min trial cap.
- **No Langfuse / Prometheus / Grafana on the host.** Those are the local
  observability stack (Docker). The hosted API degrades tracing gracefully — it
  probes once at boot, finds no collector, and continues without it.

If you'd rather have a warm, always-on link with the index baked in and no
cold-start ingest, that's the paid Railway path (`railway.toml` + `deploy.yml`)
— roughly $5 one-time. This guide is the free one.

## 1. API → Render (free)

1. Push this branch to GitHub and merge it to `main` (Render deploys `main`).
2. Render dashboard → **New +** → **Blueprint** → connect the
   `ahmdeltoky03/Qanun-RAG` repo. Render reads [`render.yaml`](render.yaml) and
   creates the free `qanun-api` web service automatically.
3. In the service → **Environment**, set the three `sync:false` secrets:
   - `COHERE_API_KEY` is used for both keys below — paste the same Cohere key
     into `QANUN_EMBEDDING_API_KEY` and `QANUN_LLM_API_KEY`.
   - `QANUN_CORS_ORIGINS` — leave for step 3 (you need the Vercel URL first);
     set it to `https://<your-vercel-app>.vercel.app`.
4. **Deploy** (or push). Watch the logs: you'll see
   `[boot] no vector index … building from corpus`, then the ingest stats, then
   `[boot] starting API`. First boot ≈ 2 min.
5. Verify: open `https://qanun-api.onrender.com/health` →
   `{"status":"ok","documents_indexed":1149,…}`. (`status:degraded` with
   `documents_indexed:0` means ingest didn't finish — check the Cohere key and
   the logs.)

> **Why native runtime, not Docker, on free?** The Dockerfile bakes the index at
> build time, which is nicer, but Render's free tier is happiest with the native
> Python runtime + the boot script that ingests on demand. Same result, no
> build-secret plumbing for the Cohere key.

## 2. UI → Vercel (free)

1. Vercel dashboard → **Add New** → **Project** → import `ahmdeltoky03/Qanun-RAG`.
2. Set **Root Directory** = `frontend` (Vercel usually detects it; confirm).
3. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL` = `https://qanun-api.onrender.com` (your Render URL).
   This is baked at build time, so it must be set **before** the first deploy.
4. **Deploy.** You get `https://<project>.vercel.app`.

`frontend/vercel.json` already pins the Next.js framework and build command, so
there's nothing else to configure.

## 3. Close the CORS loop

The UI calls the API from the browser, so the API must allow the Vercel origin.
Go back to Render → `qanun-api` → **Environment** → set:

```
QANUN_CORS_ORIGINS = https://<project>.vercel.app
```

(comma-separate if you add a custom domain later). Save → Render redeploys.
Without this the UI shows **Offline** even though `/health` works in a browser
tab. This is the #1 thing people forget.

## 4. Share and verify

Open the Vercel URL, ask a question — e.g. *"ماذا تقول المادة 147؟"* — and you
should get a cited answer with sources. Share that URL with anyone.

Quick end-to-end checks:

```bash
# API is warm and indexed
curl https://qanun-api.onrender.com/health

# A real question (Arabic in a UTF-8 file avoids shell mangling)
echo '{"question":"ماذا تقول المادة 147؟"}' > /tmp/q.json
curl -s -X POST https://qanun-api.onrender.com/ask \
  -H 'content-type: application/json' --data-binary @/tmp/q.json
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows **Offline**, `/health` works in browser | `QANUN_CORS_ORIGINS` on Render doesn't include the exact Vercel URL (scheme + host, no trailing slash) |
| `/health` → `degraded`, `documents_indexed: 0` | Ingest failed at boot — check `QANUN_EMBEDDING_API_KEY` / `QANUN_LLM_API_KEY` (both = your Cohere key) and the boot logs |
| First request takes ~2 min then works | Normal free-tier cold start: the instance woke up and rebuilt the index once |
| `429` from Cohere during boot ingest | Trial rate cap — `QANUN_EMBEDDING_RPM=18` should prevent it; if it happens, retry the deploy |
| Every answer is a refusal | Index built but under threshold — same as local; the corpus/model are fine, just ask an in-scope legal question |

## Files added on this branch

- [`scripts/start-api.sh`](scripts/start-api.sh) — boot entrypoint: ingest-if-missing, then serve on `$PORT`.
- [`render.yaml`](render.yaml) — free Render blueprint for `qanun-api`.
- [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — Railway/Vercel CLI jobs now skip when their tokens are absent, so `main` stays green on the free path.
- `DEPLOY.md` / `DEPLOY.ar.md` — this guide.
