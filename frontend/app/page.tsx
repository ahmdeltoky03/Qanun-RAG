'use client'

import { useState, useEffect, useRef } from 'react'

// ── Types ────────────────────────────────────────────────────────
interface SourceDetail {
  article_number: number
  citation: string
  chapter: string
  text_ar: string
  text_en: string
  is_repealed: boolean
}

interface AskResponse {
  answer: string
  sources: string[]
  source_details: SourceDetail[]
  flags: string[]
  out_of_scope: boolean
  blocked: boolean
  trace_id: string
  latency_ms: number
}

interface HealthResponse {
  status: string
  documents_indexed: number
  release: string
  embedding_model: string
  llm_model: string
}

// ── Quick prompts ─────────────────────────────────────────────────
const QUICK_PROMPTS = [
  'ماذا تقول المادة 147؟',
  'ما هو عقد البيع؟',
  'ما هي شروط صحة العقد؟',
  'What does Article 805 say?',
  'ما هي قواعد الإيجار؟',
]

// ── Skeleton Loader ──────────────────────────────────────────────
function SkeletonAnswer() {
  return (
    <div className="answer-card">
      <div className="answer-header">
        <div className="skeleton skeleton-line" style={{ width: 120, height: 14 }} />
        <div className="skeleton skeleton-line" style={{ width: 80, height: 14 }} />
      </div>
      <div className="answer-body">
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" style={{ width: '60%' }} />
      </div>
    </div>
  )
}

// ── Source Card (collapsible) ────────────────────────────────────
function SourceCard({ source }: { source: SourceDetail }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="source-card">
      <div className="source-header" onClick={() => setOpen(o => !o)} role="button" aria-expanded={open}>
        <div>
          <div className="source-citation">{source.citation}</div>
          <div className="source-chapter">{source.chapter}</div>
        </div>
        <div className="source-badge-row">
          {source.is_repealed && <span className="repealed-badge">ملغاة</span>}
          <span className={`chevron ${open ? 'open' : ''}`}>▼</span>
        </div>
      </div>

      <div className={`source-body ${open ? 'open' : ''}`}>
        <div className="source-divider" />
        {source.text_ar && (
          <div className="source-ar">{source.text_ar}</div>
        )}
        {source.text_en && (
          <div className="source-en">{source.text_en}</div>
        )}
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────
export default function Home() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthStatus, setHealthStatus] = useState<'loading' | 'online' | 'offline'>('loading')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  // ── Health check ───────────────────────────────────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${API}/health`, { cache: 'no-store' })
        if (res.ok) {
          const data: HealthResponse = await res.json()
          setHealth(data)
          setHealthStatus(data.status === 'ok' ? 'online' : 'offline')
        } else {
          setHealthStatus('offline')
        }
      } catch {
        setHealthStatus('offline')
      }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [API])

  // ── Ask ─────────────────────────────────────────────────────────
  const ask = async (q?: string) => {
    const query = (q ?? question).trim()
    if (!query) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await fetch(`${API}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data: AskResponse = await res.json()
      setResult(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'حدث خطأ غير متوقع')
    } finally {
      setLoading(false)
    }
  }

  const handleQuickPrompt = (prompt: string) => {
    setQuestion(prompt)
    ask(prompt)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      ask()
    }
  }

  // ── Render ──────────────────────────────────────────────────────
  return (
    <div className="page-wrapper">
      {/* ── Header ── */}
      <header className="header">
        <div className="container">
          <div className="header-inner">
            <div className="logo-group">
              <div className="logo-icon">⚖️</div>
              <div className="logo-text">
                <span className="logo-title">القانون المدني المصري</span>
                <span className="logo-subtitle">Egyptian Civil Code · RAG Q&amp;A</span>
              </div>
            </div>

            <div className={`health-badge ${healthStatus}`} title={health ? `${health.documents_indexed} articles · ${health.embedding_model} · ${health.llm_model}` : ''}>
              <span className="dot" />
              {healthStatus === 'online'
                ? `Online · ${health?.documents_indexed ?? 0} مادة`
                : healthStatus === 'loading'
                ? 'جارٍ الاتصال...'
                : 'Offline'}
            </div>
          </div>
        </div>
      </header>

      <main style={{ flex: 1 }}>
        <div className="container">

          {/* ── Hero ── */}
          <section className="hero">
            <div className="hero-eyebrow">
              <span>🏛️</span>
              <span>Hybrid RAG · 1149 Article · AR + EN</span>
            </div>
            <h1 className="hero-title">اسأل عن القانون المدني المصري</h1>
            <p className="hero-sub">
              اطرح أي سؤال قانوني بالعربية أو الإنجليزية — تحصل على إجابة مدعومة بنصوص المواد مباشرةً.
              <br />
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                General information only — not legal advice.
              </span>
            </p>
            <div className="hero-stats">
              <div className="stat">
                <div className="stat-num">1149</div>
                <div className="stat-label">مادة قانونية</div>
              </div>
              <div className="stat-divider" />
              <div className="stat">
                <div className="stat-num">AR + EN</div>
                <div className="stat-label">ثنائي اللغة</div>
              </div>
              <div className="stat-divider" />
              <div className="stat">
                <div className="stat-num">Hybrid</div>
                <div className="stat-label">Dense + BM25 + RRF</div>
              </div>
              <div className="stat-divider" />
              <div className="stat">
                <div className="stat-num">bge-m3</div>
                <div className="stat-label">Embedding Model</div>
              </div>
            </div>
          </section>

          {/* ── Search ── */}
          <section className="search-section">
            <div className="search-card">
              <div className="textarea-wrapper">
                <textarea
                  ref={textareaRef}
                  id="question-input"
                  className="search-textarea"
                  placeholder="اكتب سؤالك هنا... مثال: ماذا تقول المادة 147؟"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={3}
                  dir="rtl"
                  aria-label="Question input"
                />
              </div>

              <div className="search-footer">
                <span className="char-count">{question.length} حرف</span>
                <div className="search-actions">
                  {question && (
                    <button
                      id="clear-btn"
                      className="btn-clear"
                      onClick={() => { setQuestion(''); setResult(null); setError(null); }}
                    >
                      مسح
                    </button>
                  )}
                  <button
                    id="ask-btn"
                    className={`btn-ask ${loading ? 'loading' : ''}`}
                    onClick={() => ask()}
                    disabled={!question.trim() || loading}
                    aria-busy={loading}
                  >
                    {loading ? (
                      <>
                        <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⟳</span>
                        جارٍ البحث...
                      </>
                    ) : (
                      <> اسأل / Ask </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Quick prompts */}
            <div className="quick-prompts">
              {QUICK_PROMPTS.map(p => (
                <button
                  key={p}
                  id={`quick-${p.slice(0, 10).replace(/\s/g, '-')}`}
                  className="quick-chip"
                  onClick={() => handleQuickPrompt(p)}
                  disabled={loading}
                >
                  {p}
                </button>
              ))}
            </div>
          </section>

          {/* ── Results ── */}
          <section className="answer-section" aria-live="polite">
            {loading && <SkeletonAnswer />}

            {error && !loading && (
              <div className="answer-card" style={{ borderColor: 'rgba(248,113,113,0.3)' }}>
                <div className="answer-body">
                  <div style={{ color: 'var(--red)', fontFamily: 'var(--font-arabic)', fontSize: 16, textAlign: 'right', direction: 'rtl' }}>
                    ❌ {error}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>
                    تأكد أن الـ API Server شغال على: <code style={{ color: 'var(--blue)' }}>{API}</code>
                  </div>
                </div>
              </div>
            )}

            {result && !loading && (
              <div id="answer-section">
                {/* Answer card */}
                <div className="answer-card" style={{ marginBottom: 16 }}>
                  <div className="answer-header">
                    <div className="answer-label">
                      <span>⚖️</span>
                      <span>الإجابة</span>
                    </div>
                    <div className="answer-meta">
                      <span>{result.latency_ms.toFixed(0)} ms</span>
                      {result.sources.length > 0 && (
                        <span className="meta-tag">{result.sources.length} مادة</span>
                      )}
                      {result.out_of_scope && (
                        <span className="meta-tag" style={{ background: 'var(--gold-dim)', color: 'var(--gold-light)' }}>
                          خارج النطاق
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="answer-body">
                    <div className="answer-text">
                      {result.answer.split('\n').filter(Boolean).map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>

                    {result.flags && result.flags.length > 0 && (
                      <div className="flag-row">
                        {result.blocked && <span className="flag blocked">⛔ محجوب</span>}
                        {result.out_of_scope && <span className="flag oos">⚠️ خارج النطاق</span>}
                        {result.flags.map(f => (
                          <span key={f} className="flag injection">{f}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Trace */}
                  <div className="trace-row">
                    <span>trace: {result.trace_id}</span>
                    <span>·</span>
                    <span>{result.latency_ms.toFixed(1)} ms</span>
                    {result.flags?.length > 0 && (
                      <>
                        <span>·</span>
                        <span>flags: {result.flags.join(', ')}</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Sources */}
                {result.source_details && result.source_details.length > 0 && (
                  <div className="answer-card">
                    <div className="sources-section">
                      <div className="sources-title" style={{ paddingTop: 20 }}>
                        <span>📑</span>
                        <span>المصادر ({result.source_details.length} مادة)</span>
                      </div>
                      <div className="source-grid">
                        {result.source_details.map(s => (
                          <SourceCard key={s.article_number} source={s} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {!result && !loading && !error && (
              <div className="empty-state">
                <div className="empty-icon">📜</div>
                <div className="empty-text">اطرح سؤالك للبدء</div>
                <div className="empty-sub">ستظهر الإجابة مع المواد المستشهد بها هنا</div>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="footer">
        <div className="container">
          معلومات عامة فقط — ليست استشارة قانونية · General information only, not legal advice
          <br />
          <span style={{ color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>
            Powered by Ollama · bge-m3 · gpt-oss:20b · Qdrant · FastAPI
          </span>
        </div>
      </footer>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
