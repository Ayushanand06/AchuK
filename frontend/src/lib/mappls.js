// Loads the Mappls (MapMyIndia) Interactive JS SDK once, using the static key.
// The key is a client-side map SDK key (safe to expose in the browser, like all
// web map keys). Set it in frontend/.env as VITE_MAPPLS_KEY.

export const MAPPLS_KEY = import.meta.env.VITE_MAPPLS_KEY || ''

let loaderPromise = null

export function loadMappls() {
  if (!MAPPLS_KEY) {
    return Promise.reject(new Error('VITE_MAPPLS_KEY is not set'))
  }
  if (window.mappls && window.mappls.Map) {
    return Promise.resolve(window.mappls)
  }
  if (loaderPromise) return loaderPromise

  loaderPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    // Mappls Web SDK — static key is passed as the access_token query param.
    script.src =
      `https://sdk.mappls.com/map/sdk/web?v=3.0&layer=vector&access_token=${MAPPLS_KEY}`
    script.async = true
    script.onerror = () => reject(new Error('Failed to load Mappls SDK (check key / network)'))
    script.onload = () => {
      // SDK attaches the global asynchronously; poll briefly until ready.
      let tries = 0
      const tick = () => {
        if (window.mappls && window.mappls.Map) return resolve(window.mappls)
        if (++tries > 100) return reject(new Error('Mappls SDK loaded but global not ready'))
        setTimeout(tick, 50)
      }
      tick()
    }
    document.head.appendChild(script)
  })
  return loaderPromise
}
