import { describe, expect, it } from 'vitest'
import { type BlockRow, withLabel } from './rows'

const row: BlockRow = { id: '1', seats: 4, shape: 'line', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [] }

describe('withLabel', () => {
  it('keeps a point only for a moved letter', () => {
    expect(withLabel(row, 'moved', [1, -1])).toMatchObject({ label: 'moved', label_at: [1, -1] })
    const back = withLabel(withLabel(row, 'moved', [1, -1]), 'end')
    expect(back.label).toBe('end')
    expect(back.label_at).toBeUndefined()
    expect('label' in withLabel(back, '')).toBe(false)
  })
})
