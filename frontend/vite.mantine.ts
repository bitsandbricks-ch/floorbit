import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Plugin } from 'vite'

// The pages outside the app shell (Flask renders them with spa.render(..., shell=False)). They get
// only the Mantine styles listed in LIST; every other page gets all of them (issue #1293).
const PUBLIC_PAGES = ['src/pages/Login.tsx', 'src/pages/Checkin.tsx', 'src/pages/public/PublicStatus.tsx', 'src/pages/public/SeatHelp.tsx']
const LIST = 'src/styles/mantinePublic.ts'
// Mantine's own base styles: no component imports them, every page needs them.
const BASE = ['baseline', 'default-css-variables', 'global']

/** Keeps src/styles/mantinePublic.ts honest: the build fails when a public page uses a Mantine
 *  component whose styles aren't listed there, or when the list's order differs from Mantine's
 *  stylesheet (later rules win, so the order matters). In `npm run dev` there's no Flask to pick
 *  the styles, so the dev page loads all of them first, as Flask does for the shell's pages. */
export function mantineStyles(root: string): Plugin[] {
  const styles = resolve(root, 'node_modules/@mantine/core/styles')
  return [
    {
      name: 'floorbit-mantine-dev',
      apply: 'serve',
      transformIndexHtml: () => [{ tag: 'script', attrs: { type: 'module', src: '/src/styles/mantine.ts' }, injectTo: 'head' }],
    },
    {
      name: 'floorbit-mantine-public',
      apply: 'build',
      generateBundle(_, bundle) {
        const chunks = new Map(Object.values(bundle).flatMap((c) => (c.type === 'chunk' ? [[c.fileName, c] as const] : [])))
        const pages = PUBLIC_PAGES.map((p) => resolve(root, p))
        const used = new Set(BASE)
        const seen = new Set<string>()
        // What the entry and the public pages load. Not what they load later on (the entry's lazy
        // imports are every other page; the public pages have none).
        const walk = (file: string) => {
          const chunk = chunks.get(file)
          if (!chunk || seen.has(file)) return
          seen.add(file)
          for (const [id, mod] of Object.entries(chunk.modules)) {
            const at = id.indexOf('/@mantine/core/esm/components/')
            if (at < 0 || !mod.renderedLength) continue
            for (const part of id.slice(at).split('/').slice(5, -1)) {
              if (existsSync(resolve(styles, `${part}.css`))) used.add(part)
            }
          }
          for (const next of chunk.imports) walk(next)
        }
        for (const chunk of chunks.values()) {
          if (chunk.isEntry && chunk.name === 'index') walk(chunk.fileName)
          if (chunk.facadeModuleId && pages.includes(chunk.facadeModuleId)) walk(chunk.fileName)
        }
        if (seen.size <= 1) this.error(`mantine styles: none of ${PUBLIC_PAGES.join(', ')} is a chunk of its own any more`)

        const listed = [...readFileSync(resolve(root, LIST), 'utf8').matchAll(/styles\/([\w-]+)\.css/g)].map((m) => m[1])
        const missing = [...used].filter((n) => !listed.includes(n))
        const full = readFileSync(resolve(styles, '../styles.css'), 'utf8')
        const place = (n: string) => full.indexOf(readFileSync(resolve(styles, `${n}.css`), 'utf8').trim().slice(0, 200))
        const ordered = [...new Set([...listed, ...missing])].sort((a, b) => place(a) - place(b))
        if (missing.length || ordered.join() !== listed.join()) {
          this.error(
            `${LIST} must list ${missing.length ? `${missing.join(', ')} (a public page uses them) ` : ''}in Mantine's order:\n` +
              ordered.map((n) => `import '@mantine/core/styles/${n}.css'`).join('\n'),
          )
        }
      },
    },
  ]
}
