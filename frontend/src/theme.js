// Color + type tokens for AchuK. Two palettes (dark default + light) share the
// same semantic keys, so components can keep reading `C.<key>` unchanged. `C`
// is a live object: setTheme() mutates it in place and the app re-renders, so
// every inline style picks up the new palette.

const DARK = {
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

const LIGHT = {
  bg: '#F4F6F9',
  panel: '#FFFFFF',
  panel2: '#EDF1F6',
  border: '#DCE3EC',
  borderSoft: '#E6EBF1',
  text: '#1A2230',
  muted: '#5A6678',
  faint: '#8A94A6',
  accent: '#2F6FBF',
  accentHover: '#285FA8',
  green: '#2E9E6B',
  amber: '#B97D15',
  red: '#D23E45',
}

export const PALETTES = { dark: DARK, light: LIGHT }

// Live palette — mutated in place by setTheme so existing `import { C }` works.
export const C = { ...DARK }

export const FONT = {
  sans: "'IBM Plex Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', monospace",
}

// Status metadata stores a palette KEY (not a frozen color) so it stays correct
// after a theme switch. Resolve with C[meta.colorKey].
export const STATUS_META = {
  ok: { label: 'OK', colorKey: 'green' },
  watch: { label: 'Watch', colorKey: 'amber' },
  flag: { label: 'Flag for maintenance', colorKey: 'red' },
}

const STORAGE_KEY = 'achuk-theme'

export function initialTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'dark'
  } catch {
    return 'dark'
  }
}

export function setTheme(name) {
  const palette = PALETTES[name] || DARK
  Object.assign(C, palette)               // mutate live palette in place
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = name
  }
  try {
    localStorage.setItem(STORAGE_KEY, name)
  } catch {
    /* ignore */
  }
  return name
}

// Apply the stored/default theme immediately so the first render is correct.
setTheme(initialTheme())
