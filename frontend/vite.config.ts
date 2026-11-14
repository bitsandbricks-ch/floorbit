import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// Flask serves the built app: it reads dist's manifest (floorbit/spa.py) and renders
// templates/spa.html, so the theme from the server applies before the first paint.
const FLASK = process.env.FLOORBIT_URL || 'http://localhost:5000'

export default defineConfig({
  plugins: [react()],
  base: '/static/app/',
  resolve: {
    alias: { '@': resolve(import.meta.dirname, 'src') },
  },
  server: {
    port: 5173,
    // Local dev: everything that isn't the React app goes to Flask.
    proxy: Object.fromEntries(
      ['/api', '/login', '/logout', '/auth', '/brand', '/static/css', '/static/js', '/static/brand', '/static/fonts'].map(
        (path) => [path, { target: FLASK, changeOrigin: false }],
      ),
    ),
  },
  build: {
    outDir: resolve(import.meta.dirname, '../static/app'),
    emptyOutDir: true,
    manifest: true,
    modulePreload: { polyfill: false },
    sourcemap: false,
  },
})
