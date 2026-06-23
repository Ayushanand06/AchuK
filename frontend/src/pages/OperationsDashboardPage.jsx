import { useEffect, useState } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import Header from '../components/Header.jsx'
import Panel from '../components/Panel.jsx'

const HOUR_TICKS = ['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00', '23:00']

function pct(x) { return x == null ? '—' : (x * 100).toFixed(1) }

export default function OperationsDashboardPage({ page, onNavigate, theme, onToggleTheme }) {
  const [weekly, setWeekly] = useState(null)
  const [kpis, setKpis] = useState(null)
  const [buckets, setBuckets] = useState(null)
  const [camCount, setCamCount] = useState(0)
  const [clock, setClock] = useState('')

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      const p = (n) => String(n).padStart(2, '0')
      setClock(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`)
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  const [live, setLive] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () => {
      Promise.allSettled([api.weekly(), api.kpis(), api.buckets(), api.cameras(), api.liveStatus()]).then((r) => {
        if (!alive) return
        if (r[0].status === 'fulfilled') setWeekly(r[0].value)
        if (r[1].status === 'fulfilled') setKpis(r[1].value)
        if (r[2].status === 'fulfilled') setBuckets(r[2].value)
        if (r[3].status === 'fulfilled') setCamCount(Object.keys(r[3].value || {}).length)
        if (r[4].status === 'fulfilled') setLive(!!r[4].value.running)
      })
    }
    load()
    const poll = setInterval(load, 5000)
    return () => { alive = false; clearInterval(poll) }
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.text, fontFamily: FONT.sans }}>
      <Header page={page} onNavigate={onNavigate} theme={theme} onToggleTheme={onToggleTheme} />
      <main style={{ maxWidth: 1480, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 21, fontWeight: 500 }}>Operations dashboard</h1>
            <p style={{ margin: '5px 0 0', fontSize: 13, color: C.muted }}>Shift overview · last 7 days · Central traffic command</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {live && (
              <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.red, background: '#E2555A14', border: '1px solid #E2555A40', borderRadius: 6, padding: '3px 8px' }}>● LIVE</span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.green, animation: 'vePulse 1.6s ease-in-out infinite' }} />
              <span style={{ fontSize: 12, color: C.muted }}>{camCount} cameras online</span>
            </div>
            <div style={{ fontFamily: FONT.mono, fontSize: 16, fontWeight: 500 }}>{clock}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
          <BucketCard color={C.green} title="Auto-issued" tag="CVCS ≥ 0.80"
            count={buckets?.auto?.count} sub="challans issued" avg={buckets?.auto?.avg_cvcs} />
          <BucketCard color={C.amber} title="Awaiting review" tag="CVCS 0.55–0.80"
            count={buckets?.review?.count} sub="queued for officer" avg={buckets?.review?.avg_cvcs} />
          <BucketCard color={C.faint} title="Discarded" tag="CVCS < 0.55"
            count={null} sub="below confidence floor" notTracked />
        </div>

        <Panel style={{ padding: 0, display: 'grid', gridTemplateColumns: 'repeat(6,1fr)' }}>
          {[
            ['Auto-issue rate', pct(kpis?.auto_challan_rate), '%'],
            ['OCR accuracy', pct(kpis?.plate_ocr_accuracy), '%'],
            ['Avg review time', kpis?.avg_review_time_min ?? '—', 'min'],
            ['False-positive rate', pct(kpis?.false_positive_rate), '%'],
            ['Court-dismissal rate', pct(kpis?.court_dismissed_rate), '%'],
            ['Camera uptime', pct(kpis?.camera_uptime), '%'],
          ].map(([label, val, unit], i) => (
            <div key={label} style={{ padding: '16px 18px', borderLeft: i === 0 ? 'none' : `1px solid ${C.border}` }}>
              <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>{label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontSize: 23, fontWeight: 500 }}>{val}</span>
                <span style={{ fontSize: 13, color: C.muted }}>{unit}</span>
              </div>
            </div>
          ))}
        </Panel>

        <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16 }}>
          <ViolationsByType weekly={weekly} />
          <TopZones weekly={weekly} />
        </div>

        <HourDistribution weekly={weekly} />
      </main>
    </div>
  )
}

function BucketCard({ color, title, tag, count, sub, avg, notTracked }) {
  return (
    <Panel style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: color }} />
      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
          <span style={{ fontSize: 14, fontWeight: 500 }}>{title}</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontFamily: FONT.mono, fontSize: 11, color: '#36C5C0', background: '#36C5C014', border: '1px solid #36C5C033', borderRadius: 6, padding: '3px 8px' }}>{tag}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 38, fontWeight: 500, lineHeight: 1, letterSpacing: '-.5px', color: notTracked ? C.muted : C.text }}>
            {notTracked ? '—' : (count ?? 0).toLocaleString('en-IN')}
          </span>
          <span style={{ fontSize: 13, color: C.muted }}>{sub}</span>
        </div>
        {notTracked ? (
          <div style={{ fontSize: 12, color: C.faint, marginTop: 'auto' }}>Not tracked — discards never create a challan.</div>
        ) : (
          <div style={{ marginTop: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: C.muted }}>Avg CVCS confidence</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 12, fontWeight: 500, color: '#36C5C0' }}>{(avg ?? 0).toFixed(2)}</span>
            </div>
            <div style={{ height: 6, borderRadius: 4, background: C.panel2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${(avg ?? 0) * 100}%`, background: '#36C5C0', borderRadius: 4 }} />
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}

function ViolationsByType({ weekly }) {
  const byType = weekly?.by_type || {}
  const wow = weekly?.type_wow || {}
  const rows = Object.entries(byType).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...rows.map((r) => r[1]))
  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Violations by type</h2>
        <span style={{ fontSize: 12, color: C.faint }}>Count · week-on-week</span>
      </div>
      {rows.length === 0 ? (
        <Empty h={180} text="No violations recorded yet." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {rows.map(([type, n]) => {
            const w = wow[type]
            const up = (w ?? 0) >= 0
            return (
              <div key={type} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 60px 64px', alignItems: 'center', gap: 14 }}>
                <span style={{ fontSize: 13 }}>{type}</span>
                <div style={{ height: 8, borderRadius: 4, background: C.panel2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(n / max) * 100}%`, background: C.accent, borderRadius: 4 }} />
                </div>
                <span style={{ fontFamily: FONT.mono, fontSize: 13, textAlign: 'right' }}>{n.toLocaleString('en-IN')}</span>
                <span style={{ fontSize: 12, textAlign: 'right', color: w == null ? C.faint : up ? C.red : C.green }}>
                  {w == null ? '—' : `${up ? '▲' : '▼'} ${Math.abs(w)}%`}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}

function TopZones({ weekly }) {
  const zones = weekly?.top_zones || []
  const max = Math.max(1, ...zones.map((z) => z[1]))
  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Top zones</h2>
        <span style={{ fontSize: 12, color: C.faint }}>By volume</span>
      </div>
      {zones.length === 0 ? (
        <Empty h={180} text="No zone activity yet." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
          {zones.map(([zone, n], i) => (
            <div key={zone}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.faint, width: 14 }}>{i + 1}</span>
                <span style={{ fontSize: 13, flex: 1 }}>{zone}</span>
                <span style={{ fontFamily: FONT.mono, fontSize: 13 }}>{n}</span>
              </div>
              <div style={{ height: 4, borderRadius: 3, background: C.panel2, overflow: 'hidden', marginLeft: 24 }}>
                <div style={{ height: '100%', width: `${(n / max) * 100}%`, background: C.accent, borderRadius: 3 }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function HourDistribution({ weekly }) {
  const hours = weekly?.by_hour || []
  const max = Math.max(1, ...hours)
  const peak = hours.indexOf(Math.max(...hours, 0))
  const has = hours.some((h) => h > 0)
  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>24-hour distribution</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>Violations detected per hour</p>
        </div>
        {has && (
          <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.accent, background: '#4A90D914', border: '1px solid #4A90D933', borderRadius: 6, padding: '3px 8px' }}>
            Peak {String(peak).padStart(2, '0')}:00–{String((peak + 1) % 24).padStart(2, '0')}:00
          </span>
        )}
      </div>
      {!has ? (
        <Empty h={140} text="No hourly data yet." />
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 5, height: 140 }}>
            {(hours.length ? hours : new Array(24).fill(0)).map((v, i) => (
              <div key={i} title={`${String(i).padStart(2, '0')}:00 · ${v}`}
                style={{ flex: 1, height: `${Math.max(2, (v / max) * 100)}%`, background: i === peak ? C.accent : '#2E3744', borderRadius: '3px 3px 0 0' }} />
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontFamily: FONT.mono, fontSize: 10, color: C.faint }}>
            {HOUR_TICKS.map((t) => <span key={t}>{t}</span>)}
          </div>
        </>
      )}
    </Panel>
  )
}

function Empty({ h, text }) {
  return <div style={{ height: h, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.faint, fontSize: 13 }}>{text}</div>
}
