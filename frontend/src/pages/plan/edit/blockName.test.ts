import { describe, expect, it } from 'vitest'
import { blockName } from './blockName'

const cell = (seat: string) => ({ seat, x: 0, y: 0, hit: false, on: null })

describe('blockName', () => {
  it('is the block name when it has one', () => {
    expect(blockName({ name: ' B ', cells: [cell('B-1')] })).toBe('B')
  })
  it('falls back to the first and last seat for a block without a name', () => {
    expect(blockName({ name: '', cells: [cell('A1'), cell('A2'), cell('B12')] })).toBe('A1 – B12')
    expect(blockName({ name: '', cells: [cell('A1')] })).toBe('A1')
    expect(blockName({ name: '', cells: [] })).toBe('—')
    expect(blockName(undefined)).toBe('—')
  })
})
