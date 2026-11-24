import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { type BlockRow } from './rows'
import { RowTabs } from './RowTabs'

const row = (id: string, gap = 0): BlockRow =>
  ({ id, seats: 12, shape: 'line', gap, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [] }) as BlockRow
const rows = [row('1'), row('2', 1), row('3')]

function tabs(picked: string | null) {
  const onPick = vi.fn(), onSave = vi.fn()
  renderWithApp(<RowTabs rows={rows} name={(i) => String.fromCharCode(88 + i)} picked={picked} onPick={onPick} onSave={onSave} />)
  return { onPick, onSave }
}

describe('Row tabs', () => {
  it('has a tab per row and picks the one clicked', () => {
    const { onPick } = tabs('1')
    expect(screen.getAllByRole('tab').map((b) => b.textContent)).toEqual(['X', 'Y', 'Z'])
    expect(screen.getByRole('tab', { name: 'Row X: change it' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Row Z: change it' }))
    expect(onPick).toHaveBeenCalledWith('3')
  })

  it('adds a row and opens it', () => {
    const { onPick, onSave } = tabs('1')
    fireEvent.click(screen.getByRole('button', { name: 'Add row' }))
    const saved = onSave.mock.calls[0][0] as BlockRow[]
    expect(saved).toHaveLength(4)
    expect(onPick).toHaveBeenCalledWith(saved[3].id)
  })

  it('moves and removes the picked row, opening its neighbour', () => {
    const { onPick, onSave } = tabs('2')
    fireEvent.click(screen.getByRole('button', { name: 'Move row Y up' }))
    expect((onSave.mock.calls[0][0] as BlockRow[]).map((r) => r.id)).toEqual(['2', '1', '3'])
    fireEvent.click(screen.getByRole('button', { name: 'Take out row Y' }))
    expect((onSave.mock.calls[1][0] as BlockRow[]).map((r) => r.id)).toEqual(['1', '3'])
    expect(onPick).toHaveBeenCalledWith('1')
  })
})
