import { describe, expect, it } from 'vitest'
import { blockStep, letterIndex, nextFreeRow, nextName, rowLetter } from './tools'

describe('editor tools', () => {
  it('counts row letters like the server', () => {
    expect([0, 25, 26, 27, 51, 52].map(rowLetter)).toEqual(['A', 'Z', 'AA', 'AB', 'AZ', 'BA'])
    expect(letterIndex('AA')).toBe(26)
  })

  it('starts a new block after the rows in use', () => {
    expect(nextFreeRow([])).toBe('A')
    expect(nextFreeRow([{ naming: 'rows', row_start: 'A', rows: 2 }, { naming: 'rows', row_start: 'D', rows: 1 }, { naming: 'block', row_start: 'Q' }])).toBe('E')
    expect(nextFreeRow([{ naming: 'block', name: 'G' }, { naming: 'block', name: 'Stage' }])).toBe('H')
  })

  it('puts copies one block apart', () => {
    const v = { cols: 8, rows: 2, naming: 'rows', row_labels: 'start', name: '', rotation: 0 }
    expect(blockStep(v, 3, 'down')).toEqual({ dx: 0, dy: 2 * 3.2 + 1.6 + 3 })
    expect(blockStep(v, 3, 'right')).toEqual({ dx: 9 * 2 + 1 + 3, dy: 0 })
  })

  it('counts names up past the ones in use', () => {
    expect(nextName('PP-01', ['PP-02'])).toBe('PP-03')
    expect(nextName('Rack', ['rack 2'])).toBe('Rack 3')
  })
})
