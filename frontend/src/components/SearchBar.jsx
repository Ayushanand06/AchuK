import { useState } from 'react'
import { C, FONT } from '../theme.js'

const TABS = [
  { key: 'plate', label: 'Plate', ph: 'e.g. KA 05 MH 1534' },
  { key: 'challan', label: 'Challan ID', ph: 'e.g. VE-20260621-AB12CD34' },
  { key: 'zone', label: 'Zone', ph: 'e.g. HITEC City Signal' },
  { key: 'date', label: 'Date', ph: 'YYYY-MM-DD' },
]

export default function SearchBar({ rangeLabel, onSearch }) {
  const [type, setType] = useState('plate')
  const [q, setQ] = useState('')
  const ph = (TABS.find((t) => t.key === type) || {}).ph

  const run = () => { if (q.trim()) onSearch({ type, q }) }

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12,
      padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
    }}>
      <div style={{
        display: 'flex', gap: 4, background: C.bg, border: `1px solid ${C.border}`,
        borderRadius: 9, padding: 3,
      }}>
        {TABS.map((t) => {
          const active = t.key === type
          return (
            <button key={t.key} onClick={() => setType(t.key)} style={{
              fontFamily: FONT.sans, fontSize: 12, fontWeight: 500,
              color: active ? C.text : C.muted, background: active ? C.panel2 : 'transparent',
              border: 'none', borderRadius: 7, padding: '6px 13px', cursor: 'pointer',
            }}>{t.label}</button>
          )
        })}
      </div>

      <div style={{
        flex: 1, minWidth: 240, display: 'flex', alignItems: 'center', gap: 9,
        height: 38, padding: '0 13px', background: C.bg,
        border: `1px solid ${C.border}`, borderRadius: 9,
      }}>
        <span style={{ color: C.faint, fontSize: 14 }}>⌕</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder={ph}
          spellCheck={false}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            color: C.text, fontFamily: FONT.mono, fontSize: 13,
          }}
        />
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, height: 38, padding: '0 13px',
        background: C.bg, border: `1px solid ${C.border}`, borderRadius: 9,
        fontFamily: FONT.mono, fontSize: 12, color: C.muted,
      }}>
        <span style={{ color: C.faint }}>▦</span>{rangeLabel}
      </div>

      <button onClick={run} style={{
        fontFamily: FONT.sans, fontSize: 13, fontWeight: 500, color: C.bg,
        background: C.accent, border: 'none', borderRadius: 9,
        padding: '9px 18px', cursor: 'pointer',
      }}>Search</button>
    </div>
  )
}
