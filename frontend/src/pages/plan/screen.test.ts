import { describe, expect, it } from 'vitest'
import { troubleBlocks } from './screen'

const b = (name: string, problems = 0) => ({ name, seats: 10, online: 10 - problems, problems })

describe('troubleBlocks', () => {
  it('lists blocks with problems, most first, then by name', () => {
    const r = troubleBlocks([b('A'), b('D', 2), b('B10', 1), b('B2', 1), b('C', 0)])
    expect(r.shown.map((x) => x.name)).toEqual(['D', 'B2', 'B10'])
    expect(r.more).toBe(0)
  })

  it('says how many more there are past the limit', () => {
    const r = troubleBlocks([b('A', 1), b('B', 1), b('C', 3)], 2)
    expect(r.shown.map((x) => x.name)).toEqual(['C', 'A'])
    expect(r.more).toBe(1)
  })
})
