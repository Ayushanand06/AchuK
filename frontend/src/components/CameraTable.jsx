import { useState } from 'react'
import { C, FONT, STATUS_META } from '../theme.js'
import Panel from './Panel.jsx'

const COLS = '1.1fr 1.2fr 0.9fr 0.8fr 1fr'

function fpColor(fp) {
  return fp >= 4 ? C.red : fp >= 2.5 ? C.amber : C.text
}

export default function CameraTable({ data }) {
  const [flaggedOnly, setFlaggedOnly] = useState(false)
  const all = data?.cameras || []
  const flagN = all.filter((c) => c.status === 'flag').length
  const watchN = all.filter((c) => c.status === 'watch').length
  const rows = flaggedOnly ? all.filter((c) => c.status !== 'ok') : all

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Camera false-positive rate</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>
            {flagN} flagged for maintenance · {watchN} on watch · {all.length} cameras
          </p>
        </div>
        <button onClick={() => setFlaggedOnly((v) => !v)} style={{
          fontFamily: FONT.sans, fontSize: 12, fontWeight: 500,
          color: flaggedOnly ? C.red : C.muted,
          background: flaggedOnly ? C.red + '14' : 'transparent',
          border: `1px solid ${flaggedOnly ? C.red + '40' : C.border}`,
          borderRadius: 8, padding: '7px 12px', cursor: 'pointer',
        }}>Needs attention only</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, padding: '0 12px 10px', borderBottom: `1px solid ${C.border}` }}>
        {[
          ['Camera', 'left'], ['Zone', 'left'], ['Events · 7d', 'right'],
          ['FP rate', 'right'], ['Status', 'right'],
        ].map(([h, align]) => (
          <span key={h} style={{ fontSize: 11, color: C.faint, textAlign: align }}>{h}</span>
        ))}
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: '20px 12px', color: C.faint, fontSize: 13 }}>
          {all.length === 0 ? 'No camera activity yet.' : 'No cameras need attention.'}
        </div>
      ) : (
        rows.map((cam) => {
          const m = STATUS_META[cam.status] || STATUS_META.ok
          const mColor = C[m.colorKey]
          const flag = cam.status === 'flag'
          return (
            <div key={cam.id} style={{
              display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center',
              padding: '11px 12px', borderBottom: `1px solid ${C.borderSoft}`,
              borderLeft: `2px solid ${flag ? C.red : 'transparent'}`,
              background: flag ? C.red + '08' : 'transparent',
            }}>
              <span style={{ fontFamily: FONT.mono, fontSize: 13, color: C.text }}>{cam.id}</span>
              <span style={{ fontSize: 13, color: C.muted }}>{cam.zone}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 13, textAlign: 'right' }}>
                {(cam.events ?? 0).toLocaleString('en-IN')}
              </span>
              <span style={{ fontFamily: FONT.mono, fontSize: 13, textAlign: 'right', color: fpColor(cam.fp) }}>
                {cam.fp.toFixed(1)}%
              </span>
              <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <span style={{
                  fontSize: 11, fontWeight: 500, color: mColor, background: mColor + '14',
                  border: `1px solid ${mColor}40`, borderRadius: 6, padding: '3px 9px', whiteSpace: 'nowrap',
                }}>{m.label}</span>
              </span>
            </div>
          )
        })
      )}
    </Panel>
  )
}
