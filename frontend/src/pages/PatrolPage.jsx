import { useEffect, useRef, useState } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import { loadMappls, MAPPLS_KEY } from '../lib/mappls.js'
import Header from '../components/Header.jsx'

const DEFAULT_CENTER = { lat: 12.9716, lng: 77.5946 }
const PRIORITY = {
  critical: { label: 'Critical', color: C.red },
  high: { label: 'High', color: C.amber },
  predicted: { label: 'Predicted', color: C.accent },
}
const FILTERS = ['all', 'critical', 'high', 'predicted']

export default function PatrolPage({ page, onNavigate }) {
  const mapObj = useRef(null)
  const markers = useRef([])
  const [recs, setRecs] = useState([])
  const [lookup, setLookup] = useState({})
  const [filter, setFilter] = useState('all')
  const [mapReady, setMapReady] = useState(false)
  const [mapError, setMapError] = useState(null)

  // Load data + init map once.
  useEffect(() => {
    let cancelled = false
    api.patrol().then((r) => !cancelled && setRecs(r || [])).catch(() => {})
    api.cameras().then((cams) => {
      if (cancelled) return
      const lut = {}
      Object.values(cams || {}).forEach((c) => {
        if (c.lat && c.lng) {
          if (c.location) lut[c.location] = c
          if (c.zone) lut[c.zone] = c
        }
      })
      setLookup(lut)
    }).catch(() => {})

    if (!MAPPLS_KEY) { setMapError('nokey'); return }
    loadMappls()
      .then((mappls) => {
        if (cancelled) return
        mapObj.current = { mappls, map: new mappls.Map('patrol-map', { center: DEFAULT_CENTER, zoom: 11, zoomControl: true }) }
        setMapReady(true)
      })
      .catch((e) => !cancelled && setMapError(String(e.message || e)))
    return () => { cancelled = true }
  }, [])

  const visible = recs.filter((r) => filter === 'all' || r.priority === filter)

  // Place markers whenever filter / data / map readiness changes.
  useEffect(() => {
    if (!mapReady || !mapObj.current) return
    const { mappls, map } = mapObj.current
    markers.current.forEach((m) => { try { m.remove() } catch (_) { /* noop */ } })
    markers.current = []
    visible.forEach((r) => {
      const cam = lookup[r.zone]
      if (!cam) return
      const color = (PRIORITY[r.priority] || PRIORITY.predicted).color
      try {
        const mk = new mappls.Marker({
          map, position: { lat: cam.lat, lng: cam.lng },
          popupHtml: `<b>${r.zone}</b><br/>${r.priority} · ${r.expected} expected<br/>${r.window}`,
          html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #0B0E12;box-shadow:0 0 0 1px ${color}"></div>`,
        })
        markers.current.push(mk)
      } catch (_) { /* SDK marker variant — ignore */ }
    })
  }, [mapReady, filter, recs, lookup]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: C.bg, color: C.text, fontFamily: FONT.sans, overflow: 'hidden' }}>
      <Header page={page} onNavigate={onNavigate} />

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* MAP */}
        <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 16, padding: '16px 22px', borderBottom: `1px solid ${C.border}` }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 500 }}>Predictive patrol intelligence</h1>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>Deployment forecast · next 6 hours · 28-day rolling model</p>
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {Object.values(PRIORITY).map((p) => (
                <div key={p.label} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: p.color }} />
                  <span style={{ fontSize: 12, color: C.muted }}>{p.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, padding: 22, minHeight: 0 }}>
            <div style={{ position: 'relative', width: '100%', height: '100%', borderRadius: 14, border: `1px solid ${C.border}`, overflow: 'hidden', background: C.panel }}>
              <div id="patrol-map" style={{ width: '100%', height: '100%' }} />
              {mapError === 'nokey' && <Overlay text="Set VITE_MAPPLS_KEY in frontend/.env to enable the map." />}
              {mapError && mapError !== 'nokey' && <Overlay text={`Map failed: ${mapError}`} />}
              {!mapReady && !mapError && <Overlay text="Loading map…" />}
            </div>
          </div>
        </section>

        {/* RECOMMENDATIONS */}
        <aside style={{ width: 424, flex: 'none', borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ flex: 'none', padding: '18px 18px 14px', borderBottom: `1px solid ${C.border}` }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 500 }}>Recommended deployment</h2>
            <div style={{ display: 'flex', gap: 10 }}>
              <Stat n={visible.length} label="Zones flagged" />
              <Stat n={visible.reduce((s, r) => s + (r.units_needed || 0), 0)} label="Units needed" />
              <Stat n={visible.reduce((s, r) => s + (r.expected || 0), 0)} label="Forecast events" />
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 14 }}>
              {FILTERS.map((f) => {
                const active = filter === f
                const color = f === 'all' ? C.text : PRIORITY[f].color
                const n = f === 'all' ? recs.length : recs.filter((r) => r.priority === f).length
                return (
                  <button key={f} onClick={() => setFilter(f)} style={{
                    fontFamily: FONT.sans, fontSize: 12, fontWeight: 500, textTransform: 'capitalize',
                    color: active ? color : C.muted,
                    background: active ? (f === 'all' ? C.panel2 : color + '14') : 'transparent',
                    border: `1px solid ${active ? (f === 'all' ? C.border : color + '40') : C.border}`,
                    borderRadius: 7, padding: '5px 10px', cursor: 'pointer',
                  }}>{f} {n}</button>
                )
              })}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {visible.length === 0 && (
              <div style={{ color: C.faint, fontSize: 13, padding: 8 }}>No patrol recommendations — need ~28 days of violation history.</div>
            )}
            {visible.map((r, i) => {
              const meta = PRIORITY[r.priority] || PRIORITY.predicted
              return (
                <div key={r.zone + i} style={{ display: 'flex', border: `1px solid ${C.border}`, background: C.panel, borderRadius: 11, overflow: 'hidden' }}>
                  <div style={{ width: 3, flex: 'none', background: meta.color }} />
                  <div style={{ flex: 1, padding: '14px 15px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 500 }}>{r.zone}</span>
                      <span style={{ flex: 1 }} />
                      <span style={{ fontSize: 10, fontWeight: 500, color: meta.color, background: meta.color + '14', border: `1px solid ${meta.color}40`, borderRadius: 5, padding: '2px 7px' }}>{meta.label}</span>
                    </div>
                    <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.5, marginBottom: 12 }}>{r.reason}</div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, marginBottom: 13 }}>
                      <span style={{ fontFamily: FONT.mono, fontSize: 24, fontWeight: 500, color: meta.color, lineHeight: 1 }}>{r.expected}</span>
                      <span style={{ fontSize: 12, color: C.muted }}>violations expected</span>
                      <span style={{ fontFamily: FONT.mono, fontSize: 11, color: meta.color, background: meta.color + '14', border: `1px solid ${meta.color}40`, borderRadius: 5, padding: '2px 7px' }}>{r.multiplier}× avg</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', paddingTop: 12, borderTop: `1px solid ${C.panel2}` }}>
                      <div>
                        <div style={{ fontSize: 11, color: C.faint, marginBottom: 3 }}>Time window</div>
                        <div style={{ fontFamily: FONT.mono, fontSize: 13 }}>{r.window}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 11, color: C.faint, marginBottom: 3 }}>Units</div>
                        <div style={{ fontFamily: FONT.mono, fontSize: 13 }}>{r.units_needed} {r.units_needed > 1 ? 'units' : 'unit'}</div>
                      </div>
                      <button style={{ fontFamily: FONT.sans, fontSize: 12, fontWeight: 500, color: meta.color, background: 'transparent', border: `1px solid ${meta.color}40`, borderRadius: 8, padding: '7px 12px', cursor: 'pointer' }}>Assign →</button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </aside>
      </div>
    </div>
  )
}

function Stat({ n, label }) {
  return (
    <div style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 9, padding: '10px 12px' }}>
      <div style={{ fontFamily: FONT.mono, fontSize: 18, fontWeight: 500 }}>{n}</div>
      <div style={{ fontSize: 11, color: C.muted }}>{label}</div>
    </div>
  )
}

function Overlay({ text }) {
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, fontSize: 13, background: C.panel, textAlign: 'center', padding: 24 }}>
      {text}
    </div>
  )
}
