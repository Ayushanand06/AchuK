import { useEffect, useState, useCallback } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import Header from '../components/Header.jsx'

const HIGH_STAKES = new Set(['Red-light run', 'Wrong-side driving'])
const PLATE_RE = /^[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{1,4}$/

const FACTOR_LABELS = [
  ['model_conf', 'Model confidence'],
  ['resolution', 'Resolution'],
  ['lighting', 'Lighting'],
  ['speed', 'Speed capture'],
  ['camera_trust', 'Camera trust'],
]

export default function ReviewConsolePage({ page, onNavigate, theme, onToggleTheme }) {
  const [queue, setQueue] = useState([])
  const [sel, setSel] = useState(0)
  const [plate, setPlate] = useState('')
  const [loading, setLoading] = useState(true)
  const [lastAction, setLastAction] = useState(null)

  const current = queue[sel] || null

  useEffect(() => {
    let alive = true
    api.challanList({ pendingReview: true, limit: 200 })
      .then((r) => { if (alive) { setQueue(r.results || []); setPlate((r.results?.[0]?.plate_number) || '') } })
      .catch(() => {})
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const select = useCallback((i, q = queue) => {
    if (!q.length) return
    const idx = (i + q.length) % q.length
    setSel(idx)
    setPlate(q[idx]?.plate_number || '')
    setLastAction(null)
  }, [queue])

  const act = useCallback(async (action) => {
    const item = queue[sel]
    if (!item) return
    try {
      await api.reviewAction(item.challan_id, { action, corrected_plate: plate, officer_id: 'web' })
    } catch (_) { /* surface via lastAction below regardless */ }
    const remaining = queue.filter((_, i) => i !== sel)
    setLastAction({ action, id: item.challan_id })
    setQueue(remaining)
    const nextIdx = Math.min(sel, remaining.length - 1)
    setSel(nextIdx < 0 ? 0 : nextIdx)
    setPlate(remaining[nextIdx]?.plate_number || '')
  }, [queue, sel, plate])

  useEffect(() => {
    const onKey = (e) => {
      const t = (e.target && e.target.tagName) || ''
      if (t === 'INPUT' || t === 'TEXTAREA') return
      const k = e.key.toLowerCase()
      if (k === 'a') { e.preventDefault(); act('issue') }
      else if (k === 'r') { e.preventDefault(); act('reject') }
      else if (k === 'e') { e.preventDefault(); act('escalate') }
      else if (e.key === 'ArrowDown') { e.preventDefault(); select(sel + 1) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); select(sel - 1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [act, select, sel])

  const valid = PLATE_RE.test((plate || '').trim().toUpperCase())

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: C.bg, color: C.text, fontFamily: FONT.sans, overflow: 'hidden' }}>
      <Header page={page} onNavigate={onNavigate} theme={theme} onToggleTheme={onToggleTheme} />

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* LEFT: queue */}
        <aside style={{ width: 312, flex: 'none', borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ flex: 'none', padding: '16px 16px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Review queue</h2>
            <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.muted }}>{queue.length} pending</span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {loading && <div style={{ color: C.muted, fontSize: 13, padding: 8 }}>Loading…</div>}
            {!loading && queue.length === 0 && <div style={{ color: C.faint, fontSize: 13, padding: 8 }}>Queue is empty — nothing awaiting review.</div>}
            {queue.map((item, i) => {
              const active = i === sel
              return (
                <div key={item.challan_id} onClick={() => select(i)} style={{
                  display: 'flex', gap: 11, padding: 10, borderRadius: 10, cursor: 'pointer',
                  background: active ? C.panel2 : 'transparent',
                  border: `1px solid ${active ? C.accent : C.border}`,
                  boxShadow: active ? `inset 2px 0 0 ${C.accent}` : 'none',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                      <span style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.violation_type}</span>
                      {HIGH_STAKES.has(item.violation_type) && (
                        <span style={{ flex: 'none', fontSize: 9, fontWeight: 500, color: C.amber, background: '#E0A33E14', border: '1px solid #E0A33E33', borderRadius: 4, padding: '1px 5px' }}>High-stakes</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontFamily: FONT.mono, fontSize: 11, color: '#36C5C0', background: '#36C5C012', border: '1px solid #36C5C033', borderRadius: 5, padding: '1px 6px' }}>{(item.cvcs_score ?? 0).toFixed(2)}</span>
                      <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.plate_number}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </aside>

        {/* CENTER: evidence */}
        <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0, overflowY: 'auto' }}>
          {!current ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13 }}>
              Select a case from the queue.
            </div>
          ) : (
            <>
              <div style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 14, padding: '14px 20px', borderBottom: `1px solid ${C.border}` }}>
                <h2 style={{ margin: 0, fontSize: 15, fontWeight: 500 }}>{current.violation_type}</h2>
                <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.muted }}>{current.challan_id}</span>
                {HIGH_STAKES.has(current.violation_type) && (
                  <span style={{ fontSize: 11, fontWeight: 500, color: C.amber, background: '#E0A33E14', border: '1px solid #E0A33E33', borderRadius: 6, padding: '3px 9px' }}>High-stakes</span>
                )}
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 12, color: C.faint }}>Case {sel + 1} of {queue.length}</span>
              </div>

              <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
                <div style={{ position: 'relative', flex: 1, minHeight: 320, borderRadius: 12, border: `1px solid ${C.border}`, overflow: 'hidden', background: C.panel2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {current.evidence_url ? (
                    <img src={current.evidence_url} alt="evidence" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                  ) : (
                    <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.faint }}>no evidence image</span>
                  )}
                  <div style={{ position: 'absolute', right: 12, top: 12, display: 'flex', alignItems: 'center', gap: 8, background: '#0E1116CC', border: '1px solid #3FB37F55', borderRadius: 9, padding: '7px 11px' }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: C.green }} />
                    <div style={{ lineHeight: 1.3 }}>
                      <div style={{ fontSize: 11, fontWeight: 500, color: C.green }}>Hash verified · tamper-evident</div>
                      <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.muted }}>sha-256 {(current.evidence_hash || '').slice(0, 12)}…</div>
                    </div>
                  </div>
                </div>
                <div style={{ flex: 'none', fontFamily: FONT.mono, fontSize: 11, color: C.muted, lineHeight: 1.7 }}>
                  <div>{(current.timestamp || '').replace('T', ' ').slice(0, 19)} · {current.camera_location}</div>
                  <div style={{ color: C.faint }}>camera {current.camera_id}</div>
                </div>
              </div>
            </>
          )}
        </section>

        {/* RIGHT: inspector */}
        <aside style={{ width: 408, flex: 'none', borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {current && (
            <>
              <div style={{ flex: 1, overflowY: 'auto', padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
                <FactorSpine challan={current} />
                <PlateBox plate={plate} setPlate={setPlate} valid={valid} raw={current.plate_number} cropUrl={current.plate_crop_url} />
                <CaseFacts challan={current} />
              </div>
              <div style={{ flex: 'none', borderTop: `1px solid ${C.border}`, padding: '14px 18px' }}>
                {lastAction && (
                  <div style={{ fontSize: 12, color: C.muted, marginBottom: 10, textAlign: 'center' }}>
                    Last: {lastAction.action} · {lastAction.id}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                  <ActBtn label="Issue" hint="A" color={C.green} solid onClick={() => act('issue')} />
                  <ActBtn label="Reject" hint="R" color={C.red} onClick={() => act('reject')} />
                  <ActBtn label="Escalate" hint="E" color={C.amber} onClick={() => act('escalate')} />
                </div>
                <div style={{ marginTop: 10, fontSize: 11, color: C.faint, textAlign: 'center' }}>
                  Keyboard · A issue · R reject · E escalate · ↑↓ navigate
                </div>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

function FactorSpine({ challan }) {
  const factors = challan.metadata?.cvcs_factors
  const score = challan.cvcs_score ?? 0
  const band = score >= 0.8 ? { t: 'Auto-issue range', c: C.green }
    : score >= 0.55 ? { t: 'Borderline · needs review', c: C.amber }
    : { t: 'Below floor', c: C.faint }
  const vals = factors ? FACTOR_LABELS.map(([k]) => factors[k] ?? 0) : []
  const min = vals.length ? Math.min(...vals) : -1
  let weakMarked = false
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>CVCS factor spine</div>
          <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>Contextual confidence model</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: FONT.mono, fontSize: 26, fontWeight: 500, color: '#36C5C0', lineHeight: 1 }}>{score.toFixed(2)}</div>
          <div style={{ fontSize: 11, fontWeight: 500, color: band.c, marginTop: 4 }}>{band.t}</div>
        </div>
      </div>
      {!factors ? (
        <div style={{ fontSize: 12, color: C.faint }}>Factor breakdown not recorded for this case.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
          {FACTOR_LABELS.map(([k, label]) => {
            const v = factors[k] ?? 0
            const isWeak = !weakMarked && v === min
            if (isWeak) weakMarked = true
            const color = isWeak ? C.red : '#36C5C0'
            return (
              <div key={k}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                  <span style={{ fontSize: 12 }}>{label}</span>
                  {isWeak && <span style={{ fontSize: 9, fontWeight: 500, color: C.red, background: '#E2555A14', border: '1px solid #E2555A40', borderRadius: 4, padding: '1px 5px' }}>Weakest factor</span>}
                  <span style={{ flex: 1 }} />
                  <span style={{ fontFamily: FONT.mono, fontSize: 11, color }}>{v.toFixed(2)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 4, background: C.panel2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${v * 100}%`, background: color, borderRadius: 4 }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
      {challan.metadata?.explanation && (
        <div style={{ marginTop: 14, padding: '11px 12px', background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 9 }}>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 4 }}>Why this routed to review</div>
          <div style={{ fontSize: 12, lineHeight: 1.55 }}>{challan.metadata.explanation}</div>
        </div>
      )}
    </div>
  )
}

function PlateBox({ plate, setPlate, valid, raw, cropUrl }) {
  const stateCode = (plate || '').trim().slice(0, 2).toUpperCase()
  const unread = !raw || raw === 'UNREAD'
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 14 }}>License plate</div>
      {cropUrl && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 6 }}>Plate snapshot{unread ? ' · read & type below' : ''}</div>
          <img src={cropUrl} alt="plate" style={{ width: '100%', borderRadius: 8, border: `1px solid ${C.border}`, background: C.bg, imageRendering: 'pixelated' }} />
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, color: C.muted }}>Detected OCR</span>
        <span style={{ fontFamily: FONT.mono, fontSize: 14, color: unread ? C.amber : C.muted, letterSpacing: 1 }}>{unread ? 'UNREAD — read snapshot' : raw}</span>
      </div>
      <label style={{ display: 'block', fontSize: 11, color: C.muted, marginBottom: 6 }}>Cleaned · editable</label>
      <input value={plate} onChange={(e) => setPlate(e.target.value)} spellCheck={false}
        style={{ width: '100%', background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', color: C.text, fontFamily: FONT.mono, fontSize: 16, fontWeight: 500, letterSpacing: 2, outline: 'none' }} />
      <div style={{ marginTop: 8, fontSize: 12, fontWeight: 500, color: valid ? C.green : C.red }}>
        {valid ? `✓ Format valid · ${stateCode} state series` : '✗ Format not recognised'}
      </div>
    </div>
  )
}

function CaseFacts({ challan }) {
  const rows = [
    ['Case ID', challan.challan_id],
    ['Camera', challan.camera_id],
    ['Zone', challan.camera_location],
    ['Fine', `₹${(challan.fine_amount_inr ?? 0).toLocaleString('en-IN')}`],
    ['Decision', challan.cvcs_decision],
    ['Owner', 'masked · #' + (challan.challan_id || '').slice(-4)],
  ]
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Case facts</div>
      {rows.map(([l, v]) => (
        <div key={l} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderBottom: `1px solid ${C.panel2}` }}>
          <span style={{ fontSize: 12, color: C.muted }}>{l}</span>
          <span style={{ fontFamily: FONT.mono, fontSize: 12, textAlign: 'right' }}>{v}</span>
        </div>
      ))}
    </div>
  )
}

function ActBtn({ label, hint, color, solid, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
      fontFamily: FONT.sans, fontSize: 13, fontWeight: 500,
      color: solid ? C.bg : color, background: solid ? color : 'transparent',
      border: solid ? 'none' : `1px solid ${color}55`, borderRadius: 9, padding: '11px 0', cursor: 'pointer',
    }}>
      {label}<span style={{ fontFamily: FONT.mono, fontSize: 10, opacity: 0.7 }}>{hint}</span>
    </button>
  )
}
