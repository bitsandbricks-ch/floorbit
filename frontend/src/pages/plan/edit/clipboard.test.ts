import { describe, expect, it } from 'vitest'
import { copies, deltaTo, rawOf } from './clipboard'

describe('editor clipboard', () => {
  const block = rawOf('block', { id: 'b1', hall_id: 'main', name: '', naming: 'rows', row_start: 'A', rows: 2, cols: 8, x: 30, y: 40, extra: 1 })
  const wall = rawOf('mark', { id: 'w1', hall_id: 'main', kind: 'wall', x: 10, y: 10, x2: 20, y2: 10 })

  it('keeps what the server takes back, not ids or halls', () => {
    expect(block.body).toEqual({ name: '', naming: 'rows', row_start: 'A', rows: 2, cols: 8, x: 30, y: 40 })
    expect(wall.body).toEqual({ kind: 'wall', x: 10, y: 10, x2: 20, y2: 10 })
  })

  it('moves copies and gives blocks the next free rows', () => {
    const inUse = [{ naming: 'rows', row_start: 'A', rows: 2 }]
    const [b, w] = copies([block, wall], { x: 2, y: 3.2 }, inUse)
    expect(b.body).toMatchObject({ x: 32, y: 43.2, row_start: 'C' })
    expect(w.body).toMatchObject({ x: 12, y: 13.2, x2: 22, y2: 13.2 })
    const two = copies([block, block], { x: 0, y: 0 }, inUse)
    expect(two.map((r) => r.body.row_start)).toEqual(['C', 'E'])
  })

  it('renames block-named blocks by letter', () => {
    const named = rawOf('block', { naming: 'block', name: 'G', x: 1, y: 1 })
    expect(copies([named], { x: 0, y: 0 }, [{ naming: 'block', name: 'G' }])[0].body.name).toBe('H')
  })

  it('pastes the first item at the pointer', () => {
    expect(deltaTo([block, wall], { x: 50, y: 50 })).toEqual({ x: 20, y: 10 })
  })
})
