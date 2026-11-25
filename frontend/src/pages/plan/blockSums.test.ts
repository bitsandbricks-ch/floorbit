import { describe, expect, it } from 'vitest'
import type { PlanBlock, PlanShape } from '@/api/types'
import { blockSums, shapeLabel, shapeRect } from './blockSums'

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

describe('shapeRect', () => {
  it('boxes a block with its outline padding, turned blocks included', () => {
    expect(shapeRect(shape({ cx: 100, cy: 50, w: 40, h: 20 }))).toEqual([74, 34, 126, 66])
    const [x0, y0, x1, y1] = shapeRect(shape({ cx: 0, cy: 0, w: 40, h: 20, rotation: 90 }))
    expect([x1 - x0, y1 - y0].map(Math.round)).toEqual([32, 52])
  })
})
