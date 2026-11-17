import { describe, expect, it } from 'vitest'
import type { PowerMarkers } from '@/api/types'
import { boardLoads } from './powerLoad'

const circuit = (board: string, state: string, pct: number | null) => ({ id: Math.random().toString(), name: 'c', board, state, pct, seats: [], switches: [] })

describe('board load on the power layer', () => {
  it('takes the busiest circuit and the worst state per board', () => {
    const power = { circuits: [circuit('a', 'ok', 40), circuit('a', 'warn', 82), circuit('a', 'unknown', null), circuit('b', 'tripped', null)] } as unknown as PowerMarkers
    const loads = boardLoads(power)
    expect(loads.get('a')).toEqual({ pct: 82, state: 'warn', circuits: 3, tripped: 0 })
    expect(loads.get('b')).toEqual({ pct: null, state: 'tripped', circuits: 1, tripped: 1 })
  })
})
