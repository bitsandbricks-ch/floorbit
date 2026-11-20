import { describe, expect, it } from 'vitest'
import type { PlanDrawing, PlanShape } from '@/api/types'
import { areaView, blockLabel, findBlock } from './model'

const shape = (over: Partial<PlanShape>): PlanShape => ({ cx: 100, cy: 100, rotation: 0, w: 64, h: 64, name: '', cells: [{ x: 0, y: 0, seat: 'A-1' } as PlanShape['cells'][number]], ...over })

describe('seat blocks in a plan pane (#1012)', () => {
  it('names a block by its name, its row letters, or its first seat', () => {
    expect(blockLabel(shape({ name: 'North' }))).toEqual({ name: 'North' })
    expect(blockLabel(shape({ rows: [{ text: 'A', x: 0, y: 0 }, { text: 'A', x: 9, y: 0 }, { text: 'D', x: 0, y: 9 }] }))).toEqual({ rows: 'A–D' })
    expect(blockLabel(shape({}))).toEqual({ seat: 'A-1' })
  })
  it('finds a block by id, or by the name older panes saved', () => {
    const drawing = { shapes: [shape({ id: 'b1' }), shape({ id: 'b2', name: 'South', cx: 500 })], box: '', cell: 32 } as PlanDrawing
    expect(findBlock(drawing, 'b1')?.id).toBe('b1')
    expect(findBlock(drawing, 'South')?.id).toBe('b2')
    expect(findBlock(drawing, '')).toBeUndefined()
    expect(areaView({ kind: 'block', id: 'b1' }, drawing)).not.toBeNull()
  })
})
