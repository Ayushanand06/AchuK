import { useEffect, useState } from 'react'
import { C, FONT } from '../theme.js'
import { api } from '../api.js'
import Header from '../components/Header.jsx'
import SearchBar from '../components/SearchBar.jsx'
import SearchResults from '../components/SearchResults.jsx'
import TrendChart from '../components/TrendChart.jsx'
import DecisionDonut from '../components/DecisionDonut.jsx'
import ZoneHourHeatmap from '../components/ZoneHourHeatmap.jsx'
import CameraTable from '../components/CameraTable.jsx'

const RANGE_LABEL = 'Last 7 days'

export default function AnalyticsPage({ page = 'analytics', onNavigate }) {
  const [weekly, setWeekly] = useState(null)
  const [zoneHour, setZoneHour] = useState(null)
  const [cameras, setCameras] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [search, setSearch] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.allSettled([api.weekly(), api.zoneHour(), api.cameraReport()])
      .then(([w, z, c]) => {
        if (!alive) return
        if (w.status === 'fulfilled') setWeekly(w.value)
        if (z.status === 'fulfilled') setZoneHour(z.value)
        if (c.status === 'fulfilled') setCameras(c.value)
        if (w.status === 'rejected' && z.status === 'rejected' && c.status === 'rejected') {
          setLoadError('Could not reach the backend. Is it running on :8000?')
        }
      })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const onSearch = async ({ type, q }) => {
    setSearch({ loading: true, error: null, data: null, query: { type, q } })
    try {
      const data = await api.searchChallans({ type, q })
      setSearch({ loading: false, error: null, data, query: { type, q } })
    } catch (e) {
      setSearch({ loading: false, error: String(e.message || e), data: null, query: { type, q } })
    }
  }

  const exportReport = () => {
    const blob = new Blob([JSON.stringify({ weekly, zoneHour, cameras }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'visionenforce-analytics.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.text, fontFamily: FONT.sans }}>
      <Header page={page} onNavigate={onNavigate} />

      <main style={{ maxWidth: 1480, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 21, fontWeight: 500, letterSpacing: '.1px' }}>Analytics &amp; reporting</h1>
            <p style={{ margin: '5px 0 0', fontSize: 13, color: C.muted }}>{RANGE_LABEL} · all zones · enforcement performance</p>
          </div>
          <button onClick={exportReport} style={{
            fontFamily: FONT.sans, fontSize: 13, fontWeight: 500, color: C.text,
            background: C.panel2, border: `1px solid ${C.border}`,
            borderRadius: 9, padding: '8px 14px', cursor: 'pointer',
          }}>Export report</button>
        </div>

        {loadError && (
          <div style={{ background: C.red + '14', border: `1px solid ${C.red}40`, color: C.red, borderRadius: 12, padding: '12px 16px', fontSize: 13 }}>
            {loadError}
          </div>
        )}

        <SearchBar rangeLabel={RANGE_LABEL} onSearch={onSearch} />
        <SearchResults state={search} onClear={() => setSearch(null)} />

        <div style={{ display: 'grid', gridTemplateColumns: '1.9fr 1fr', gap: 16 }}>
          <TrendChart weekly={weekly} loading={loading} />
          <DecisionDonut weekly={weekly} />
        </div>

        <ZoneHourHeatmap data={zoneHour} />
        <CameraTable data={cameras} />
      </main>
    </div>
  )
}
