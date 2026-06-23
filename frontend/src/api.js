const BASE = import.meta.env.VITE_API_BASE || ''

async function getJSON(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

async function postJSON(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

export const api = {
  weekly: () => getJSON('/api/analytics/weekly'),
  kpis: () => getJSON('/api/analytics/kpis'),
  zoneHour: () => getJSON('/api/analytics/zone-hour'),
  cameraReport: () => getJSON('/api/analytics/camera-report'),
  buckets: () => getJSON('/api/analytics/buckets'),
  patrol: () => getJSON('/api/analytics/patrol'),
  mapData: () => getJSON('/api/map-data'),
  cameras: () => getJSON('/api/map/cameras'),

  challanList: ({ pendingReview = false, limit = 200 } = {}) => {
    const qs = new URLSearchParams({ limit: String(limit) })
    if (pendingReview) qs.set('pending_review', 'true')
    return getJSON('/api/challans?' + qs.toString())
  },
  challan: (id) => getJSON('/api/challans/' + encodeURIComponent(id)),
  reviewAction: (id, body) =>
    postJSON('/api/challans/' + encodeURIComponent(id) + '/review', body),

  liveStatus: () => getJSON('/api/live/status'),
  liveStart: () => postJSON('/api/live/start', {}),
  liveStop: () => postJSON('/api/live/stop', {}),
  liveFocus: (id) => postJSON('/api/live/focus/' + encodeURIComponent(id), {}),
  liveFrameUrl: (id, bust) =>
    `${BASE}/api/live/cameras/${encodeURIComponent(id)}/frame.jpg?t=${bust}`,
  liveStreamUrl: (id, run) =>
    `${BASE}/api/live/cameras/${encodeURIComponent(id)}/stream.mjpg?s=${run}`,

  searchChallans({ type, q }) {
    const param = { plate: 'plate', challan: 'challan', zone: 'zone', date: 'date' }[type] || 'plate'
    if (param === 'challan') {
      return getJSON('/api/challans/' + encodeURIComponent(q.trim()))
        .then((r) => ({ count: 1, results: [r] }))
        .catch(() => ({ count: 0, results: [] }))
    }
    const qs = new URLSearchParams({ [param]: q.trim(), limit: '50' })
    return getJSON('/api/challans?' + qs.toString())
  },
}
