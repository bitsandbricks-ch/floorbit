import { describe, expect, it } from 'vitest'
import { paneAt, paneKey } from './large'

const text = (t: string) => ({ pane: { kind: 'text' as const, text: t, size: 'm' as const, align: 'start' as const } })
const sections = [{ panels: [
  { x: 0, y: 0, w: 8, h: 4, node: text('A') },
  { x: 8, y: 0, w: 8, h: 4, node: { split: 'row' as const, sizes: [50, 50], children: [text('B'), text('C')] } },
] }]

describe('make large', () => {
  it('finds the pane a key names, in splits too', () => {
    expect(paneKey(0, 1, [1])).toBe('0.1.1')
    expect(paneAt(sections as never, '0.0')).toMatchObject({ text: 'A' })
    expect(paneAt(sections as never, '0.1.1')).toMatchObject({ text: 'C' })
  })

  it('shows the dashboard when the key no longer fits it', () => {
    expect(paneAt(sections as never, '0.5')).toBeNull()
    expect(paneAt(sections as never, '0.1')).toBeNull()   // a split, not a pane
    expect(paneAt(sections as never, 'x.0')).toBeNull()
  })
})
