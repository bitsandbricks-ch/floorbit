import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlanGroup, SeatViewData } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { ItemList } from './ItemList'

const shape = (id: string, cx: number) => ({ id, group: null, cx, cy: 100, rotation: 0, w: 100, h: 40, name: id, cells: [] })
const data = {
  size: { w: 1600, h: 1000, cell: 32 }, seats: {}, blocks: [], halls: [], hall: 'main',
  switches: [{ id: 's1', name: 'sw-a-01', status: 'up', x: 50, y: 50 }],
  drawing: {
    shapes: [shape('A', 100), shape('B', 300)], box: { x: 0, y: 0, w: 1600, h: 1000 }, cell: 32,
    marks: [{ id: 'm1', kind: 'text', x: 10, y: 10, text: 'Stage' }, { id: 'm2', kind: 'zone', x: 0, y: 0, w: 10, h: 10, label: 'Bar' }],
  },
} as unknown as SeatViewData
const groups: PlanGroup[] = [
  { id: 'g1', name: 'Front', members: [{ kind: 'block', id: 'A' }, { kind: 'mark', id: 'm1' }, { kind: 'mark', id: 'gone' }] },
  // A group whose items are mostly gone is not shown.
  { id: 'g2', name: 'Ghost', members: [{ kind: 'mark', id: 'x' }, { kind: 'block', id: 'B' }] },
]

function setup() {
  const onSelect = vi.fn(), onRename = vi.fn(), onUngroup = vi.fn()
  renderWithApp(<ItemList data={data} groups={groups} selected={[]} onSelect={onSelect} onRename={onRename} onUngroup={onUngroup} />)
  return { onSelect, onRename, onUngroup }
}

describe('Items list', () => {
  it('lists groups first, then the rest by kind', () => {
    setup()
    expect(screen.getByText('Front')).toBeInTheDocument()
    expect(screen.queryByText('Ghost')).toBeNull()
    const rows = screen.getAllByRole('button').map((b) => b.textContent).filter(Boolean)
    expect(rows.indexOf('Seat block B')).toBeLessThan(rows.indexOf('Switch sw-a-01'))
    expect(rows.indexOf('Switch sw-a-01')).toBeLessThan(rows.indexOf('Zone: Bar'))
    expect(screen.getByText('5 items')).toBeInTheDocument()
  })

  it('picks an item, a whole group, and adds with Shift', () => {
    const { onSelect } = setup()
    fireEvent.click(screen.getByText('Zone: Bar'))
    expect(onSelect).toHaveBeenLastCalledWith([{ kind: 'mark', id: 'm2' }], false)
    fireEvent.click(screen.getByText('Front'), { shiftKey: true })
    expect(onSelect).toHaveBeenLastCalledWith([{ kind: 'block', id: 'A' }, { kind: 'mark', id: 'm1' }], true)
  })

  it('finds by name, also inside groups', () => {
    setup()
    fireEvent.change(screen.getByPlaceholderText('Find an item'), { target: { value: 'stage' } })
    expect(screen.getByText('Label: Stage')).toBeInTheDocument()
    expect(screen.queryByText('Zone: Bar')).toBeNull()
  })

  it('renames and takes apart a group', () => {
    const { onRename, onUngroup } = setup()
    fireEvent.doubleClick(screen.getByText('Front'))
    const input = screen.getByLabelText('Group name')
    fireEvent.change(input, { target: { value: 'Stage area' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith(expect.objectContaining({ id: 'g1' }), 'Stage area')
    fireEvent.click(screen.getByRole('button', { name: 'Ungroup' }))
    expect(onUngroup).toHaveBeenCalledWith(expect.objectContaining({ id: 'g1' }))
  })
})
