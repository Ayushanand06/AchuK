import { C } from '../theme.js'
import Panel from './Panel.jsx'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const W = 700, H = 200, PAD_TOP = 20

// Map a 7-length series to SVG points across the viewBox.
function toPoints(series, max) {
  const n = series.length
  return series.map((v, i) => {
    const x = n === 1 ? 0 : (i / (n - 1)) * W
    const y = PAD_TOP + (1 - (max ? v / max : 0)) * (H - PAD_TOP)
    return [Math.round(x), Math.round(y)]
  })
}

export default function TrendChart({ weekly, loading }) {
  const series = weekly?.by_day || []
  const total = series.reduce((a, b) => a + b, 0)
  const max = Math.max(1, ...series)
  const pts = toPoints(series.length ? series : new Array(7).fill(0), max)
  const line = pts.map((p) => p.join(',')).join(' ')
  const area = `0,${H} ` + line + ` ${W},${H}`

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Violation trend</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>Daily detections · this week</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 14, height: 2, background: C.accent }} />
          <span style={{ fontSize: 11, color: C.muted }}>This week</span>
        </div>
      </div>

      {loading || total > 0 ? (
        <>
          <svg viewBox={`0 0 ${W} ${H + 20}`} preserveAspectRatio="none" style={{ width: '100%', height: 220, display: 'block' }}>
            {[40, 100, 160].map((y) => (
              <line key={y} x1="0" y1={y} x2={W} y2={y} stroke={C.panel2} strokeWidth="1" />
            ))}
            <polygon points={area} fill="#4A90D914" />
            <polyline points={line} fill="none" stroke={C.accent} strokeWidth="2.5" />
            {pts.map((p, i) => (
              <circle key={i} cx={p[0]} cy={p[1]} r="3.5" fill={C.accent} />
            ))}
          </svg>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: C.faint }}>
            {DAYS.map((d) => <span key={d}>{d}</span>)}
          </div>
        </>
      ) : (
        <Empty />
      )}
    </Panel>
  )
}

function Empty() {
  return (
    <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13 }}>
      No detections this week yet.
    </div>
  )
}
