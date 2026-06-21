// Color + type tokens taken from the VisionEnforce design system.
export const C = {
  bg: '#0E1116',
  panel: '#171B22',
  panel2: '#1C212A',
  border: '#252A33',
  borderSoft: '#1C212A',
  text: '#E6E9EF',
  muted: '#8B93A1',
  faint: '#5C6675',
  accent: '#4A90D9',
  accentHover: '#5BA0E6',
  green: '#3FB37F',
  amber: '#E0A33E',
  red: '#E2555A',
}

export const FONT = {
  sans: "'IBM Plex Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', monospace",
}

// Status metadata for the camera table.
export const STATUS_META = {
  ok: { label: 'OK', color: C.green },
  watch: { label: 'Watch', color: C.amber },
  flag: { label: 'Flag for maintenance', color: C.red },
}
