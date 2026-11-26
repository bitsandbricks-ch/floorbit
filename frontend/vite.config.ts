import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { mantineStyles } from './vite.mantine.ts'

// Flask serves the built app: it reads dist's manifest (floorbit/spa.py) and renders
// templates/spa.html, so the theme from the server applies before the first paint.
const FLASK = process.env.FLOORBIT_URL || 'http://localhost:5000'

export default defineConfig({
  plugins: [react(), mantineStyles(import.meta.dirname)],
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
    rollupOptions: {
      // Mantine's styles are entries of their own: Flask links all of them, or for the pages
      // outside the shell only those they use, ahead of the app's styles (floorbit/spa.py).
      input: {
        index: resolve(import.meta.dirname, 'index.html'),
        mantine: resolve(import.meta.dirname, 'src/styles/mantine.ts'),
        mantinePublic: resolve(import.meta.dirname, 'src/styles/mantinePublic.ts'),
      },
    },
  },
})
