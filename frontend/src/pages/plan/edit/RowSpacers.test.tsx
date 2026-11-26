import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { type BlockRow } from './rows'
import { RowSeatStrip } from './RowSeatStrip'
import { RowTabs } from './RowTabs'

const row = (id: string, gap = 0): BlockRow =>
  ({ id, seats: 4, shape: 'line', gap, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [] }) as BlockRow
const rows = [row('1'), row('2', 1), row('3')]
const name = (i: number) => String.fromCharCode(88 + i)

describe('Spacers between rows (#1547)', () => {
  it('adds a spacer above a row that has none', () => {
    const onSave = vi.fn()
    renderWithApp(<RowTabs rows={rows} name={name} picked="3" onPick={() => {}} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: 'Spacer above Z' }))
    expect(onSave).toHaveBeenCalledWith([rows[0], rows[1], { ...rows[2], gap: 1 }])
  })

  it('removes the spacer above a row', () => {
    const onSave = vi.fn()
    renderWithApp(<RowTabs rows={rows} name={name} picked="2" onPick={() => {}} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove the spacer above row Y' }))
    expect(onSave).toHaveBeenCalledWith([rows[0], { ...rows[1], gap: 0 }, rows[2]])
  })

  it('shows a small cue between the tabs, without a label', () => {
    const { container } = renderWithApp(<RowTabs rows={rows} name={name} picked="1" onPick={() => {}} onSave={() => {}} />)
    expect(container.querySelectorAll('.fb-row-spacer-cue')).toHaveLength(1)
    expect(screen.getAllByRole('tab').map((b) => b.textContent)).toEqual(['X', 'Y', 'Z'])
  })
})

describe('Gaps inside a row (#1547)', () => {
  it('adds a gap between two seats with a click', () => {
    const onSave = vi.fn()
    renderWithApp(<RowSeatStrip seats={4} gaps={[]} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add a gap after seat 2' }))
    expect(onSave).toHaveBeenCalledWith([{ after: 2, size: 1 }])
  })

  it('sizes and removes a gap that is clicked', () => {
    const onSave = vi.fn()
    renderWithApp(<RowSeatStrip seats={4} gaps={[{ after: 1, size: 1 }]} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: 'Gap after seat 1, 1 seat' }))
    const size = screen.getByLabelText('Size of the gap after seat 1, in seats')
    fireEvent.change(size, { target: { value: '2.5' } })
    fireEvent.blur(size)
    expect(onSave).toHaveBeenLastCalledWith([{ after: 1, size: 2.5 }])
    fireEvent.click(screen.getByRole('button', { name: 'Remove the gap after seat 1' }))
    expect(onSave).toHaveBeenLastCalledWith([])
  })
})
