#!/usr/bin/env pwsh
# =================================================================
# git-setup.ps1 — Initialize Git repo with branching strategy
# Run once: .\scripts\git-setup.ps1 -Remote "https://github.com/YOUR/REPO.git"
# =================================================================

param(
    [string]$Remote = "",
    [string]$DefaultBranch = "main"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "`n  → $msg" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  ⚖️  Qanun-RAG Git Setup" -ForegroundColor Yellow
Write-Host "  ════════════════════════" -ForegroundColor DarkGray

# ── Initial commit ──────────────────────────────────────────────
Write-Step "Staging all files..."
git add -A

Write-Step "Creating initial commit..."
git commit -m "feat: initial project structure

- Standard Python ML layout: src/, tests/, data/, scripts/
- FastAPI RAG service with hybrid retrieval (dense + BM25 + RRF)
- Egyptian Civil Code corpus (1149 articles, AR + EN)
- Guardrails: prompt injection, PII masking, citation check
- Observability: Prometheus, Grafana, Langfuse
- Docker Compose + nginx canary
- CI: lint + test + quality gate + image build
- Next.js 14 UI (Arabic RTL, dark mode, glassmorphism)
- Ollama via ngrok tunnel (qwen2.5:7b-instruct + bge-m3)
- Deploy targets: Railway (API) + Vercel (UI)

Closes #1 — Project Foundation
"

# ── Rename to main ──────────────────────────────────────────────
Write-Step "Setting default branch to '$DefaultBranch'..."
git branch -M $DefaultBranch

# ── Feature branches ─────────────────────────────────────────────
$branches = @(
    "feat/project-structure",
    "feat/corpus-pipeline",
    "feat/rag-engine",
    "feat/api-observability",
    "feat/evaluation",
    "feat/ollama-ngrok",
    "feat/nextjs-ui",
    "feat/deployment"
)

Write-Step "Creating feature branches..."
foreach ($branch in $branches) {
    git branch $branch
    Write-Host "    ✅ $branch" -ForegroundColor Green
}

# ── Add remote ───────────────────────────────────────────────────
if ($Remote -ne "") {
    Write-Step "Adding remote: $Remote"
    git remote add origin $Remote
    
    Write-Step "Pushing main branch..."
    git push -u origin $DefaultBranch
    
    Write-Host ""
    Write-Host "  🎉 Done! Pushed to GitHub." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  ✅ Local setup complete." -ForegroundColor Green
    Write-Host "  💡 To push to GitHub, run:" -ForegroundColor Yellow
    Write-Host "     git remote add origin https://github.com/YOUR/REPO.git" -ForegroundColor DarkGray
    Write-Host "     git push -u origin main" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  📌 Branches created:" -ForegroundColor Cyan
git branch --list | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
Write-Host ""
