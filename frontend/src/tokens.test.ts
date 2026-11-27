/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Floorbit styles with the shared --bnb-* tokens (#1274); the old --color-* names are gone, from
// the React app and from the brand CSS the server pages load. Read from disk: Vitest hands CSS
// imports over empty.
const SRC = join(import.meta.dirname)
const STATIC = join(SRC, '../../static/css')
const SKIP = new Set(['tokens.test.ts'])
const files = (readdirSync(SRC, { recursive: true }) as string[])
  .map((f) => f.split('\\').join('/'))
  .filter((f) => /\.(ts|tsx|css)$/.test(f) && !SKIP.has(f))

describe('design tokens', () => {
  it('reads --bnb-* everywhere', () => {
    const brand = (readdirSync(STATIC, { recursive: true }) as string[])
      .map((f) => f.split('\\').join('/')).filter((f) => f.endsWith('.css'))
    const old = [...files.map((f) => join(SRC, f)), ...brand.map((f) => join(STATIC, f))].flatMap((f) =>
      readFileSync(f, 'utf8').split('\n')
        .flatMap((line, i) => (/--color-[a-z]/.test(line) ? [`${f}:${i + 1}: ${line.trim()}`] : [])))
    expect(files.filter((f) => f.endsWith('.css')).length).toBeGreaterThan(20)
    expect(brand).toContain('brand/tokens.css')
    expect(old).toEqual([])
  })
})
