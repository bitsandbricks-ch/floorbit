import { describe, expect, it } from 'vitest'
import type { PlanBlock, PlanShape } from '@/api/types'
import { blockSums, placeLabels, placesAround, shapeLabel, shapeRect } from './blockSums'

const shape = (over: Partial<PlanShape> = {}): PlanShape => ({ cx: 0, cy: 0, rotation: 0, w: 100, h: 20, name: '', cells: [], ...over })
const sum = (over: Partial<PlanBlock> = {}): PlanBlock => ({ name: '', seats: 60, online: 60, problems: 0, ...over })

describe('blockSums', () => {
  it('gives unnamed blocks their own counts, not the first block\'s (#1322)', () => {
    const got = blockSums([shape(), shape(), shape()], [sum({ online: 21 }), sum({ online: 40 }), sum({ online: 59 })])
    expect(got.map((b) => b?.online)).toEqual([21, 40, 59])
  })
  it('matches by id when both sides have one', () => {
    const got = blockSums([shape({ id: 'b' }), shape({ id: 'a' })], [sum({ id: 'a', online: 1 }), sum({ id: 'b', online: 2 })])
    expect(got.map((b) => b?.online)).toEqual([2, 1])
  })
  it('leaves a block out rather than guess when the lists differ', () => {
    expect(blockSums([shape(), shape()], [sum()])).toEqual([undefined, undefined])
  })
})

describe('shapeLabel', () => {
  it('uses the name, then the rows, then the first seat', () => {
    expect(shapeLabel(shape({ name: 'VIP' }))).toBe('VIP')
    expect(shapeLabel(shape({ rows: [{ text: 'G', x: 0, y: 0 }, { text: 'H', x: 0, y: 0 }] }))).toBe('G–H')
    expect(shapeLabel(shape({ cells: [{ seat: '101', x: 0, y: 0 }] as PlanShape['cells'] }))).toBe('101')
  })
})

describe('placeLabels', () => {
  // Twelve blocks of two rows, 22 units apart: a 30 unit label doesn't fit between them (#1323).
  const blocks = Array.from({ length: 12 }, (_, i) => shape({ cx: 200, cy: 100 + i * 42 }))
  const rects = blocks.map(shapeRect)

  it('never draws two labels on top of each other or on another block', () => {
    const items = rects.map((r) => ({ places: placesAround(r, 60, 30, 4), rank: 0 }))
    const at = placeLabels(items, rects)
    const boxes = [...at].map(([i, k]) => items[i].places[k])
    for (const a of boxes) for (const b of boxes) {
      if (a === b) continue
      const apart = Math.abs(a.x - b.x) * 2 >= a.w + b.w || a.y + a.h <= b.y || b.y + b.h <= a.y
      expect(apart).toBe(true)
    }
    for (const [i, k] of at) {
      const p = items[i].places[k]
      rects.forEach((r, j) => {
        if (j === i) return
        const clear = p.x + p.w / 2 <= r[0] || p.x - p.w / 2 >= r[2] || p.y + p.h <= r[1] || p.y >= r[3]
        expect(clear).toBe(true)
      })
    }
    // The top one fits above; the others move beside their block.
    expect(at.get(0)).toBe(0)
    expect(at.size).toBeGreaterThan(1)
  })

  it('lets a block with problems pick before its quiet neighbour', () => {
    const two = [shape({ cx: 0, cy: 0 }), shape({ cx: 0, cy: 10 })]
    const items = two.map((_, i) => ({ places: [{ x: 0, y: -40, w: 50, h: 20 }], rank: i }))
    expect([...placeLabels(items).keys()]).toEqual([1])
  })
})
