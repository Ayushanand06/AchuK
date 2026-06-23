import { useEffect, useRef, useState } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import Header from '../components/Header.jsx'

export default function LiveWallPage({ page, onNavigate, theme, onToggleTheme }) {
  const [status, setStatus] = useState({ running: false, cameras: [], focus: null })
  const [busy, setBusy] = useState(false)
  const [runToken, setRunToken] = useState(0)
  const pollRef = useRef(null)

  const refresh = () => api.liveStatus().then(setStatus).catch(() => {})

  useEffect(() => {
    refresh()
    pollRef.current = setInterval(refresh, 2000)
    return () => clearInterval(pollRef.current)
  }, [])

  const toggle = async () => {
    setBusy(true)
    try {
      const s = status.running ? await api.liveStop() : await api.liveStart()
      if (!status.running) setRunToken((t) => t + 1)
      setStatus(s)
    } catch (e) {
      alert('Live feed error: ' + (e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const focusCam = async (id) => {
    setStatus((s) => ({ ...s, focus: id }))
    try { await api.liveFocus(id) } catch {}
  }

  const cams = status.cameras || []
  const totalViolations = cams.reduce((s, c) => s + (c.violations || 0), 0)

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.text, fontFamily: FONT.sans }}>
      <Header page={page} onNavigate={onNavigate} theme={theme} onToggleTheme={onToggleTheme} />
      <main style={{ maxWidth: 1480, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 21, fontWeight: 500 }}>Live camera wall</h1>
            <p style={{ margin: '5px 0 0', fontSize: 13, color: C.muted }}>
              {cams.length} junction feeds · {status.running
                ? `${totalViolations} violations this session · click a tile to run it at full rate`
                : 'feeds stopped'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {status.running && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: C.red, animation: 'vePulse 1.6s ease-in-out infinite' }} />
                <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.red }}>LIVE</span>
              </div>
            )}
            <button onClick={toggle} disabled={busy} style={{
              fontFamily: FONT.sans, fontSize: 13, fontWeight: 500,
              color: status.running ? C.red : C.bg,
              background: status.running ? 'transparent' : C.green,
              border: status.running ? `1px solid ${C.red}55` : 'none',
              borderRadius: 9, padding: '9px 18px', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1,
            }}>{busy ? '…' : status.running ? 'Stop feeds' : 'Start feeds'}</button>
          </div>
        </div>

        {cams.length === 0 ? (
          <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13, border: `1px solid ${C.border}`, borderRadius: 12 }}>
            {status.running ? 'Warming up feeds…' : 'Press “Start feeds” to begin live detection across all cameras.'}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {cams.map((cam) => (
              <CameraTile
                key={cam.camera_id}
                cam={cam}
                running={status.running}
                focused={status.focus === cam.camera_id}
                runToken={runToken}
                onFocus={() => focusCam(cam.camera_id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

function CameraTile({ cam, running, focused, runToken, onFocus }) {
  const fresh = cam.last_seen && (Date.now() - new Date(cam.last_seen).getTime()) < 8000
  const dot = running && fresh ? C.green : running ? C.amber : C.faint
  return (
    <div
      onClick={running ? onFocus : undefined}
      title={running ? 'Run this camera at full rate' : ''}
      style={{
        background: C.panel,
        border: `1px solid ${focused ? C.accent : C.border}`,
        boxShadow: focused ? `0 0 0 1px ${C.accent}` : 'none',
        borderRadius: 12, overflow: 'hidden', cursor: running ? 'pointer' : 'default',
      }}
    >
      <div style={{ position: 'relative', aspectRatio: '16 / 9', background: '#0B0E12' }}>
        {running ? (
          <img
            src={api.liveStreamUrl(cam.camera_id, runToken)}
            alt={cam.camera_id}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        ) : (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontFamily: FONT.mono, fontSize: 12 }}>offline</div>
        )}
        <div style={{ position: 'absolute', left: 10, top: 10, display: 'flex', alignItems: 'center', gap: 6, background: '#0E1116AA', borderRadius: 6, padding: '3px 8px' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: dot }} />
          <span style={{ fontFamily: FONT.mono, fontSize: 11, color: '#E6E9EF' }}>{cam.camera_id}</span>
        </div>
        {focused && running && (
          <div style={{ position: 'absolute', left: 10, bottom: 10, fontFamily: FONT.mono, fontSize: 10, color: '#0E1116', background: C.accent, borderRadius: 6, padding: '2px 7px', fontWeight: 600 }}>
            FOCUS · full rate
          </div>
        )}
        <div style={{ position: 'absolute', right: 10, top: 10, fontFamily: FONT.mono, fontSize: 11, color: '#E6E9EF', background: '#0E1116AA', borderRadius: 6, padding: '3px 8px' }}>
          {cam.violations} viol.
        </div>
      </div>
      <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{cam.location}</div>
          <div style={{ fontSize: 11, color: C.muted }}>{cam.zone} · {cam.frames} frames</div>
        </div>
        <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.faint, whiteSpace: 'nowrap' }}>{cam.clip}</span>
      </div>
    </div>
  )
}
