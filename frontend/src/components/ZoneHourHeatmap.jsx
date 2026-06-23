import { C, FONT } from '../theme.js'
import Panel from './Panel.jsx'

const HOUR_TICKS = ['00', '03', '06', '09', '12', '15', '18', '21', '23']

function cellBg(v, max) {
  const a = (0.07 + (max ? v / max : 0) * 0.9).toFixed(3)
  return `rgba(74,144,217,${a})`
}

export default function ZoneHourHeatmap({ data }) {
  const zones = data?.zones || []
  const matrix = data?.matrix || []
  const max = data?.max || 0
  const hasData = zones.length > 0 && max > 0

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Zone × hour intensity</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>Violations detected by zone and hour of day</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: C.faint }}>Fewer</span>
          {[0.12, 0.38, 0.64, 0.92].map((a) => (
            <span key={a} style={{ width: 16, height: 12, borderRadius: 2, background: `rgba(74,144,217,${a})` }} />
          ))}
          <span style={{ fontSize: 11, color: C.faint }}>More</span>
        </div>
      </div>

      {!hasData ? (
        <div style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13 }}>
          No zone activity yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {zones.map((zone, zi) => (
            <div key={zone} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 104, flex: 'none', fontSize: 12, color: C.muted,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }} title={zone}>{zone}</span>
              <div style={{ flex: 1, display: 'flex', gap: 3 }}>
                {(matrix[zi] || []).map((v, h) => (
                  <div key={h}
                    title={`${zone} · ${String(h).padStart(2, '0')}:00 · ${v} events`}
                    style={{ flex: 1, height: 24, borderRadius: 3, background: cellBg(v, max) }} />
                ))}
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}>
            <span style={{ width: 104, flex: 'none' }} />
            <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between', fontFamily: FONT.mono, fontSize: 10, color: C.faint }}>
              {HOUR_TICKS.map((t) => <span key={t}>{t}</span>)}
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}
