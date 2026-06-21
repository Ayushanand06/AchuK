import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies API + media to the FastAPI backend so the app is
// same-origin during development. Override with VITE_BACKEND_ORIGIN when
// running against a non-default host.
const BACKEND = process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/evidence': { target: BACKEND, changeOrigin: true },
      '/videos': { target: BACKEND, changeOrigin: true },
      '/frames': { target: BACKEND, changeOrigin: true },
    },
  },
})
