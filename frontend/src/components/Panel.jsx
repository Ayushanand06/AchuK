import { C } from '../theme.js'

// Standard dashboard card.
export default function Panel({ children, style }) {
  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`,
      borderRadius: 12, padding: 20, ...style,
    }}>
      {children}
    </div>
  )
}
