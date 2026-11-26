/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// The React app styles with the shared --bnb-* tokens (#1274). Only styles/bnb.css still reads
// Floorbit's own --color-* names, to feed the shared ones from the brand tokens and the theme.
// Read from disk: Vitest hands CSS imports over empty.
const SRC = join(import.meta.dirname)
const SKIP = new Set(['styles/bnb.css', 'tokens.test.ts'])
const files = (readdirSync(SRC, { recursive: true }) as string[])
  .map((f) => f.split('\\').join('/'))
  .filter((f) => /\.(ts|tsx|css)$/.test(f) && !SKIP.has(f))

describe('design tokens', () => {
  it('reads --bnb-* everywhere but the bridge', () => {
    const old = files.flatMap((f) => readFileSync(join(SRC, f), 'utf8').split('\n')
      .flatMap((line, i) => (/--color-[a-z]/.test(line) ? [`${f}:${i + 1}: ${line.trim()}`] : [])))
    expect(files.filter((f) => f.endsWith('.css')).length).toBeGreaterThan(20)
    expect(old).toEqual([])
  })
})
