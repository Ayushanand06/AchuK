import { C, FONT } from '../theme.js'
import Panel from './Panel.jsx'

function fmt(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

export default function DecisionDonut({ weekly }) {
  const total = weekly?.total || 0
  const auto = weekly?.auto_challan || 0
  const reviewed = Math.max(0, total - auto)

  const segments = total > 0
    ? [
        { label: 'Auto-issued', value: auto, color: C.green },
        { label: 'Reviewed', value: reviewed, color: C.amber },
      ]
    : []

  let offset = 0
  const arcs = segments.map((s) => {
    const pct = total ? (s.value / total) * 100 : 0
    const arc = { ...s, pct, dash: `${pct.toFixed(1)} 100`, dashoffset: -offset }
    offset += pct
    return arc
  })

  return (
    <Panel style={{ display: 'flex', flexDirection: 'column' }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 500 }}>Decision split</h2>

      {total === 0 ? (
        <div style={{ flex: 1, minHeight: 128, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13 }}>
          No decisions yet.
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, flex: 1 }}>
          <div style={{ position: 'relative', width: 128, height: 128, flex: 'none' }}>
            <svg viewBox="0 0 200 200" style={{ width: 128, height: 128, transform: 'rotate(-90deg)' }}>
              <circle cx="100" cy="100" r="80" fill="none" stroke={C.panel2} strokeWidth="22" />
              {arcs.map((a, i) => (
                <circle key={i} cx="100" cy="100" r="80" fill="none" stroke={a.color}
                  strokeWidth="22" pathLength="100" strokeDasharray={a.dash} strokeDashoffset={a.dashoffset} />
              ))}
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: FONT.mono, fontSize: 19, fontWeight: 500 }}>{fmt(total)}</span>
              <span style={{ fontSize: 10, color: C.muted }}>decisions</span>
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {arcs.map((a) => (
              <div key={a.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 9, height: 9, borderRadius: 2, background: a.color }} />
                <span style={{ fontSize: 12, flex: 1 }}>{a.label}</span>
                <span style={{ fontFamily: FONT.mono, fontSize: 12, fontWeight: 500 }}>{a.pct.toFixed(1)}%</span>
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: 0.6 }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: C.faint }} />
              <span style={{ fontSize: 12, flex: 1 }}>Discarded</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 11 }}>not stored</span>
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}
