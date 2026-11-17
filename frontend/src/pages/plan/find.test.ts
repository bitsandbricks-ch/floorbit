import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { findPlace } from './find'

const shape = (name: string, cx: number) => ({ name, cx, cy: 100, w: 64, h: 32, rotation: 0, cells: [] })
const data = {
  drawing: { shapes: [shape('C', 300), shape('Stage left', 900)], box: '0 0 1600 1000', cell: 32 },
  switches: [
    { id: '1', name: 'sw-c-01', status: 'up', x: 320, y: 60 },
    { id: '2', name: 'sw-c-02', status: 'up', x: 360, y: 60 },
    { id: '3', name: 'core-1', status: 'up', x: 800, y: 20 },
  ],
} as unknown as Pick<SeatViewData, 'drawing' | 'switches'>

describe('findPlace', () => {
  it('finds a block or a switch by its name, however it is typed', () => {
    expect(findPlace(' c ', data)).toEqual({ kind: 'block', name: 'C', at: { x: 300, y: 100 } })
    expect(findPlace('stage_left', data)?.name).toBe('Stage left')
    expect(findPlace('SW-C-02', data)).toEqual({ kind: 'switch', name: 'sw-c-02', at: { x: 360, y: 60 } })
  })

  it('takes the start of a switch name only when one switch has it', () => {
    expect(findPlace('core', data)?.name).toBe('core-1')
    expect(findPlace('sw-c', data)).toBeNull()
    expect(findPlace('co', data)).toBeNull()
    expect(findPlace('', data)).toBeNull()
  })
})
