import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { navShell } from './buildtools/nav-shell'

// Flask serves the built app: it reads dist's manifest (floorbit/spa.py) and renders
// templates/spa.html, so the theme from the server applies before the first paint.
const FLASK = process.env.FLOORBIT_URL || 'http://localhost:5000'

/** static/app/nav-shell.json: what Flask needs to draw the sidebar in the first paint (templates/_nav.html). */
function navShellFile(): Plugin {
  return {
    name: 'floorbit-nav-shell',
    apply: 'build',
    generateBundle() {
      const source = JSON.stringify(navShell(resolve(import.meta.dirname, 'src/i18n')))
      this.emitFile({ type: 'asset', fileName: 'nav-shell.json', source })
    },
  }
}

export default defineConfig({
  plugins: [react(), navShellFile()],
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
    // Two entries: the React app, and the sidebar alone for the pages Flask draws (floorbit/spa.py).
    rollupOptions: {
      input: {
        index: resolve(import.meta.dirname, 'index.html'),
        nav: resolve(import.meta.dirname, 'src/nav/entry.tsx'),
      },
    },
  },
})
