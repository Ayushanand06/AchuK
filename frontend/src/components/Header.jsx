import { C, FONT } from '../theme.js'

const NAV = [
  { label: 'Dashboard', key: 'dashboard' },
  { label: 'Cameras', key: 'live' },
  { label: 'Review queue', key: 'review' },
  { label: 'Patrol', key: 'patrol' },
  { label: 'Map', key: 'map' },
  { label: 'Analytics', key: 'analytics' },
]

export default function Header({ page = 'analytics', onNavigate }) {
  return (
    <header
      style={{
        position: 'sticky', top: 0, zIndex: 30, display: 'flex', alignItems: 'center',
        gap: 24, height: 56, padding: '0 24px', background: C.bg,
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 24, height: 24, borderRadius: 7, background: C.panel2,
          border: `1px solid ${C.border}`, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{ width: 9, height: 9, background: C.text, transform: 'rotate(45deg)', borderRadius: 1 }} />
        </div>
        <span style={{ fontSize: 15, fontWeight: 500, letterSpacing: '.2px' }}>VisionEnforce</span>
      </div>

      <nav style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: 8 }}>
        {NAV.map((n) => {
          const active = n.key && n.key === page
          const clickable = !!n.key
          return (
            <button
              key={n.label}
              onClick={() => clickable && onNavigate && onNavigate(n.key)}
              disabled={!clickable}
              title={clickable ? '' : 'Coming soon'}
              style={{
                fontFamily: FONT.sans, fontSize: 13, fontWeight: active ? 500 : 400,
                color: active ? C.text : C.muted,
                background: active ? C.panel2 : 'transparent',
                border: `1px solid ${active ? C.border : 'transparent'}`,
                padding: '6px 12px', borderRadius: 8,
                cursor: clickable ? 'pointer' : 'default',
                opacity: clickable ? 1 : 0.7,
              }}
            >{n.label}</button>
          )
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        paddingLeft: 16, borderLeft: `1px solid ${C.border}`,
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%', background: C.panel2,
          border: `1px solid ${C.border}`, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 12, fontWeight: 500,
        }}>RM</div>
        <div style={{ lineHeight: 1.25 }}>
          <div style={{ fontSize: 12, fontWeight: 500 }}>Insp. R. Mehta</div>
          <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.muted }}>#4471 · day shift</div>
        </div>
      </div>
    </header>
  )
}
