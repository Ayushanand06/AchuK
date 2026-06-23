import { useEffect, useRef, useState } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import { loadMappls, MAPPLS_KEY } from '../lib/mappls.js'
import Header from '../components/Header.jsx'
import Panel from '../components/Panel.jsx'

const DEFAULT_CENTER = { lat: 12.9716, lng: 77.5946 } // Bengaluru
const DEFAULT_ZOOM = 11

export default function MapPage({ page, onNavigate, theme, onToggleTheme }) {
  const mapEl = useRef(null)
  const mapObj = useRef(null)
  const [status, setStatus] = useState('loading') // loading | ready | error | nokey
  const [error, setError] = useState(null)
  const [payload, setPayload] = useState(null)

  useEffect(() => {
    if (!MAPPLS_KEY) { setStatus('nokey'); return }
    let cancelled = false

    Promise.all([
      loadMappls(),
      api.mapData().catch(() => ({ pins: [], heatmap: [], summary: {} })),
      api.cameras().catch(() => ({})),
    ])
      .then(([mappls, data, cams]) => {
        if (cancelled) return
        setPayload(data)
        renderMap(mappls, 've-map', mapObj, data, cams)
        setStatus('ready')
      })
      .catch((e) => { if (!cancelled) { setError(String(e.message || e)); setStatus('error') } })

    return () => { cancelled = true }
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.text, fontFamily: FONT.sans }}>
      <Header page={page} onNavigate={onNavigate} theme={theme} onToggleTheme={onToggleTheme} />
      <main style={{ maxWidth: 1480, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 21, fontWeight: 500 }}>Violation map</h1>
          <p style={{ margin: '5px 0 0', fontSize: 13, color: C.muted }}>
            Live camera nodes and violation hotspots · Mappls
          </p>
        </div>

        {status === 'nokey' && (
          <Panel>
            <p style={{ margin: 0, fontSize: 13, color: C.amber }}>
              Map key not set. Add <code>VITE_MAPPLS_KEY=your_static_key</code> to
              <code> frontend/.env</code> and restart <code>npm run dev</code>.
            </p>
          </Panel>
        )}
        {status === 'error' && (
          <Panel><p style={{ margin: 0, fontSize: 13, color: C.red }}>Map failed to load: {error}</p></Panel>
        )}

        <div style={{ position: 'relative' }}>
          <div
            id="ve-map"
            ref={mapEl}
            style={{
              width: '100%', height: 620, borderRadius: 12,
              border: `1px solid ${C.border}`, overflow: 'hidden', background: C.panel,
            }}
          />
          {status === 'ready' && payload?.summary && (
            <SummaryCard summary={payload.summary} colors={payload.violation_colors} />
          )}
          {status === 'loading' && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
              justifyContent: 'center', color: C.muted, fontSize: 13,
            }}>Loading map…</div>
          )}
        </div>
      </main>
    </div>
  )
}

function SummaryCard({ summary, colors }) {
  const types = Object.entries(summary.by_type || {})
  return (
    <div style={{
      position: 'absolute', top: 14, right: 14, width: 240, background: C.panel + 'F2',
      border: `1px solid ${C.border}`, borderRadius: 12, padding: 14, backdropFilter: 'blur(4px)',
    }}>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>
        {summary.total_violations ?? 0} violations
      </div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 10 }}>
        Top zone: {summary.top_zone || 'N/A'}
      </div>
      {types.length === 0 ? (
        <div style={{ fontSize: 12, color: C.faint }}>No violations plotted yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {types.map(([t, n]) => (
            <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: (colors || {})[t] || C.accent }} />
              <span style={{ fontSize: 12, flex: 1 }}>{t}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 12 }}>{n}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Builds the map: camera nodes (always), violation pins, heatmap circles.
function renderMap(mappls, el, mapRef, data, cams) {
  const pins = data?.pins || []
  const heat = data?.heatmap || []
  const colors = data?.violation_colors || {}
  const camList = Object.values(cams || {})

  // Center on the first pin / camera if available.
  const first = pins[0] || camList[0]
  const center = first ? { lat: first.lat, lng: first.lng } : DEFAULT_CENTER

  const map = new mappls.Map(el, { center, zoom: DEFAULT_ZOOM, zoomControl: true })
  mapRef.current = map

  const place = () => {
    // Camera nodes (neutral markers).
    camList.forEach((c) => safeMarker(mappls, map, c.lat, c.lng,
      `<b>${c.camera_id}</b><br/>${c.location || ''} · ${c.zone || ''}`, C.muted))

    // Heatmap intensity circles per zone.
    heat.forEach((z) => safeCircle(mappls, map, z.lat, z.lng,
      300 + (z.intensity || 0) * 900))

    // Violation pins, coloured by type.
    pins.forEach((p) => safeMarker(mappls, map, p.lat, p.lng,
      `<b>${p.violation_type}</b><br/>${p.plate_number || ''}<br/>${p.zone || ''} · CVCS ${p.cvcs_score ?? ''}`,
      colors[p.violation_type] || C.accent))
  }

  // SDK fires 'load' when tiles are ready; place immediately too as a fallback.
  if (typeof map.on === 'function') map.on('load', place)
  place()
}

function safeMarker(mappls, map, lat, lng, html, color) {
  try {
    new mappls.Marker({
      map, position: { lat, lng }, popupHtml: html,
      icon_url: undefined, fitbounds: false,
      html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid #0E1116;box-shadow:0 0 0 1px ${color}"></div>`,
    })
  } catch (_) { /* SDK variant without html marker — ignore */ }
}

function safeCircle(mappls, map, lat, lng, radius) {
  try {
    new mappls.Circle({
      map, center: { lat, lng }, radius,
      fillColor: '#4A90D9', fillOpacity: 0.18, strokeColor: '#4A90D9', strokeOpacity: 0.4, strokeWeight: 1,
    })
  } catch (_) { /* Circle may be unavailable in some SDK builds — ignore */ }
}
