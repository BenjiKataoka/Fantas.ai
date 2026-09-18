import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    // Pin the origin. Without this, Vite silently drifts to 3001/3002 when 3000 is
    // busy — and since Clerk's session AND localStorage league creds are per-origin,
    // a drifting port makes you appear signed out with your credentials wiped every
    // time. Fail loudly on a busy port instead so the origin stays stable.
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
