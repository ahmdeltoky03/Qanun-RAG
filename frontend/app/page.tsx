'use client'

import { useState, useEffect, useRef, useCallback } from 'react'

// ── Types ────────────────────────────────────────────────────────
interface SourceDetail {
  article_number: number
  citation: string
  chapter: string
  section?: string
  score?: number
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

type Phase = 'idle' | 'connecting' | 'streaming' | 'done'

// ── Quick prompts ─────────────────────────────────────────────────
// A pool of realistic Civil-Code questions; the UI shows a random sample of
// these (re-rolled on load and via the shuffle button) so the chips feel alive.
const QUICK_POOL = [
  'ماذا تقول المادة 147؟',
  'ما هو عقد البيع؟',
  'ما هي شروط صحة العقد؟',
  'What does Article 805 say?',
  'ما هي قواعد الإيجار؟',
  'ما هي المسؤولية التقصيرية؟',
  'ما حكم التعويض عن الضرر؟',
  'ما هي مدة التقادم؟',
  'ما هو الرهن الرسمي؟',
  'ما هي شروط الوكالة؟',
  'متى ينفسخ العقد؟',
  'ما هي التزامات البائع؟',
  'ما هو حق الملكية؟',
  'What is unjust enrichment?',
]
const QUICK_COUNT = 5

function samplePrompts(n: number): string[] {
  const pool = [...QUICK_POOL]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, n)
}

// ── SSE helpers ───────────────────────────────────────────────────
// The backend streams `event: <name>\ndata: <json>\n\n`. EventSource is
// GET-only, so we parse the SSE frames manually off a fetch() body reader.
function parseSSEFrame(raw: string): { event: string; data: string } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }
  if (!dataLines.length) return null
  return { event, data: dataLines.join('\n') }
}

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
        {source.text_ar && <div className="source-ar">{source.text_ar}</div>}
        {source.text_en && <div className="source-en">{source.text_en}</div>}
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────
export default function Home() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResponse | null>(null)
  const [streamText, setStreamText] = useState('')
  const [ttft, setTtft] = useState<number | null>(null) // ms until the first streamed token
  const [phase, setPhase] = useState<Phase>('idle')
  const [meta, setMeta] = useState<{ sources: string[]; trace_id: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthStatus, setHealthStatus] = useState<'loading' | 'online' | 'offline'>('loading')
  // Deterministic on first render (SSR-safe); randomised in an effect after mount.
  const [prompts, setPrompts] = useState<string[]>(() => QUICK_POOL.slice(0, QUICK_COUNT))
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const answerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const busy = phase === 'connecting' || phase === 'streaming'

  const articleCount = health?.documents_indexed ?? 1149
  const embeddingModel = health?.embedding_model ?? 'bge-m3'
  const llmModel = health?.llm_model ?? 'qwen2.5:7b-instruct'

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

  // ── Auto-scroll while tokens stream in ─────────────────────────
  useEffect(() => {
    if (phase === 'streaming' && answerRef.current) {
      answerRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [streamText, phase])

  // ── Randomise the quick-prompt chips once on the client ────────
  useEffect(() => {
    setPrompts(samplePrompts(QUICK_COUNT))
  }, [])

  // ── Ask (SSE streaming) ─────────────────────────────────────────
  const ask = useCallback(
    async (q?: string) => {
      const query = (q ?? question).trim()
      if (!query) return

      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl

      setResult(null)
      setStreamText('')
      setTtft(null)
      setMeta(null)
      setError(null)
      setPhase('connecting')

      const t0 = performance.now()
      let firstToken = false
      try {
        const res = await fetch(`${API}/ask/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: query }),
          signal: ctrl.signal,
        })

        if (!res.ok || !res.body) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `HTTP ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })

          let sep: number
          while ((sep = buf.indexOf('\n\n')) !== -1) {
            const frame = buf.slice(0, sep)
            buf = buf.slice(sep + 2)
            const ev = parseSSEFrame(frame)
            if (!ev) continue

            if (ev.event === 'meta') {
              const d = JSON.parse(ev.data)
              setMeta({ sources: d.sources ?? [], trace_id: d.trace_id ?? '' })
              setPhase('streaming')
            } else if (ev.event === 'token') {
              const d = JSON.parse(ev.data)
              if (!firstToken) {
                firstToken = true
                setTtft(performance.now() - t0)
              }
              setPhase('streaming')
              setStreamText(prev => prev + (d.text ?? ''))
            } else if (ev.event === 'done') {
              const d: AskResponse = JSON.parse(ev.data)
              setResult(d)
              setStreamText(d.answer ?? '')
              setPhase('done')
            }
          }
        }
        // If the stream ended without a done frame, settle to whatever we have.
        setPhase(p => (p === 'done' ? 'done' : streamText ? 'done' : 'idle'))
      } catch (e: unknown) {
        if ((e as { name?: string })?.name === 'AbortError') return
        setError(e instanceof Error ? e.message : 'حدث خطأ غير متوقع')
        setPhase('idle')
      }
    },
    [question, API, streamText]
  )

  const stop = () => {
    abortRef.current?.abort()
    setPhase(streamText ? 'done' : 'idle')
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

  const reset = () => {
    abortRef.current?.abort()
    setQuestion('')
    setResult(null)
    setStreamText('')
    setTtft(null)
    setMeta(null)
    setError(null)
    setPhase('idle')
  }

  const shownAnswer = result?.answer ?? streamText
  const isStreaming = phase === 'streaming'

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

            <div
              className={`health-badge ${healthStatus}`}
              title={health ? `${health.documents_indexed} articles · ${health.embedding_model} · ${health.llm_model}` : ''}
            >
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
              <span>Hybrid RAG · {articleCount} Article · AR + EN</span>
            </div>
            <h1 className="hero-title">محاميك اللي قاري الـ {articleCount} مادة… وكله ببلاش</h1>
            <p className="hero-sub">
              اسأل براحتك بالعربي أو الإنجليزي — تجيلك الإجابة مع المواد اللي بتسندها.
              <br />
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                General information only — not legal advice.
              </span>
            </p>
            <div className="hero-stats">
              <div className="stat">
                <div className="stat-num">{articleCount}</div>
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
                <div className="stat-num">{embeddingModel}</div>
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
                  {question && !busy && (
                    <button id="clear-btn" className="btn-clear" onClick={reset}>
                      مسح
                    </button>
                  )}
                  {busy ? (
                    <button id="stop-btn" className="btn-stop" onClick={stop}>
                      <span className="stop-square" /> إيقاف
                    </button>
                  ) : (
                    <button
                      id="ask-btn"
                      className="btn-ask"
                      onClick={() => ask()}
                      disabled={!question.trim()}
                      aria-busy={busy}
                    >
                      اسأل / Ask
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Quick prompts (random sample + shuffle) */}
            <div className="quick-prompts">
              {prompts.map(p => (
                <button
                  key={p}
                  id={`quick-${p.slice(0, 10).replace(/\s/g, '-')}`}
                  className="quick-chip"
                  onClick={() => handleQuickPrompt(p)}
                  disabled={busy}
                >
                  {p}
                </button>
              ))}
              <button
                className="quick-chip quick-shuffle"
                onClick={() => setPrompts(samplePrompts(QUICK_COUNT))}
                disabled={busy}
                title="أسئلة تانية"
                aria-label="Shuffle questions"
              >
                🔄
              </button>
            </div>
          </section>

          {/* ── Results ── */}
          <section className="answer-section" aria-live="polite" ref={answerRef}>
            {phase === 'connecting' && <SkeletonAnswer />}

            {error && phase !== 'connecting' && (
              <div className="answer-card" style={{ borderColor: 'rgba(248,113,113,0.3)' }}>
                <div className="answer-body">
                  <div
                    style={{
                      color: 'var(--red)',
                      fontFamily: 'var(--font-arabic)',
                      fontSize: 16,
                      textAlign: 'right',
                      direction: 'rtl',
                    }}
                  >
                    ❌ {error}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>
                    تأكد أن الـ API Server شغال على: <code style={{ color: 'var(--blue)' }}>{API}</code>
                  </div>
                </div>
              </div>
            )}

            {(isStreaming || result) && !error && (
              <div id="answer-section">
                {/* Answer card */}
                <div className="answer-card" style={{ marginBottom: 16 }}>
                  <div className="answer-header">
                    <div className="answer-label">
                      <span>⚖️</span>
                      <span>الإجابة</span>
                    </div>
                    <div className="answer-meta">
                      {isStreaming && <span className="live-tag"><span className="live-dot" /> مباشر</span>}
                      {result && (
                        <span>
                          {ttft != null && <>أول رد في {(ttft / 1000).toFixed(2)}s · </>}
                          الإجمالي {result.latency_ms.toFixed(0)} ms
                        </span>
                      )}
                      {(result?.sources.length ?? meta?.sources.length ?? 0) > 0 && (
                        <span className="meta-tag">{(result?.sources ?? meta?.sources ?? []).length} مادة</span>
                      )}
                      {result?.out_of_scope && (
                        <span
                          className="meta-tag"
                          style={{ background: 'var(--gold-dim)', color: 'var(--gold-light)' }}
                        >
                          خارج النطاق
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="answer-body">
                    <div className="answer-text">
                      {shownAnswer.split('\n').filter(Boolean).map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                      {isStreaming && <span className="stream-caret" />}
                    </div>

                    {result && result.flags && result.flags.length > 0 && (
                      <div className="flag-row">
                        {result.blocked && <span className="flag blocked">⛔ محجوب</span>}
                        {result.out_of_scope && <span className="flag oos">⚠️ خارج النطاق</span>}
                        {result.flags.map(f => (
                          <span key={f} className="flag injection">
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Trace */}
                  {(result || meta?.trace_id) && (
                    <div className="trace-row">
                      <span>trace: {result?.trace_id ?? meta?.trace_id}</span>
                      {result && (
                        <>
                          <span>·</span>
                          <span>ttft {ttft != null ? `${ttft.toFixed(0)} ms` : '—'}</span>
                          <span>·</span>
                          <span>total {result.latency_ms.toFixed(1)} ms</span>
                        </>
                      )}
                      {result?.flags && result.flags.length > 0 && (
                        <>
                          <span>·</span>
                          <span>flags: {result.flags.join(', ')}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Sources */}
                {result?.source_details && result.source_details.length > 0 && (
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

            {!result && phase === 'idle' && !error && (
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
            Powered by Ollama · {embeddingModel} · {llmModel} · Qdrant · FastAPI
          </span>
        </div>
      </footer>
    </div>
  )
}
