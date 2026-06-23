import { C, FONT } from '../theme.js'
import Panel from './Panel.jsx'

export default function SearchResults({ state, onClear }) {
  if (!state) return null
  const { loading, error, data, query } = state
  const results = data?.results || []

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Search results</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: C.muted }}>
            {query.type} · “{query.q}”{!loading && !error ? ` · ${results.length} found` : ''}
          </p>
        </div>
        <button onClick={onClear} style={{
          fontFamily: FONT.sans, fontSize: 12, fontWeight: 500, color: C.muted,
          background: 'transparent', border: `1px solid ${C.border}`,
          borderRadius: 8, padding: '7px 12px', cursor: 'pointer',
        }}>Clear</button>
      </div>

      {loading && <div style={{ color: C.muted, fontSize: 13, padding: '8px 0' }}>Searching…</div>}
      {error && <div style={{ color: C.red, fontSize: 13, padding: '8px 0' }}>Search failed: {error}</div>}
      {!loading && !error && results.length === 0 && (
        <div style={{ color: C.muted, fontSize: 13, padding: '8px 0' }}>No matching challans.</div>
      )}

      {results.length > 0 && (
        <div>
          <div style={{
            display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1.2fr 0.8fr 1fr',
            gap: 12, padding: '0 12px 10px', borderBottom: `1px solid ${C.border}`,
          }}>
            {['Challan', 'Type', 'Plate', 'Zone', 'CVCS', 'When'].map((h, i) => (
              <span key={h} style={{ fontSize: 11, color: C.faint, textAlign: i >= 4 ? 'right' : 'left' }}>{h}</span>
            ))}
          </div>
          {results.map((r) => (
            <div key={r.challan_id} style={{
              display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1.2fr 0.8fr 1fr',
              gap: 12, alignItems: 'center', padding: '11px 12px', borderBottom: `1px solid ${C.borderSoft}`,
            }}>
              <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.text }}>{r.challan_id}</span>
              <span style={{ fontSize: 13, color: C.muted }}>{r.violation_type}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 13 }}>{r.plate_number}</span>
              <span style={{ fontSize: 13, color: C.muted }}>{r.camera_location}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 13, textAlign: 'right' }}>{(r.cvcs_score ?? 0).toFixed(2)}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.muted, textAlign: 'right' }}>
                {(r.timestamp || '').replace('T', ' ').slice(0, 16)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
