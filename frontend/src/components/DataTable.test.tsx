import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useLocation } from 'react-router-dom'
import { renderWithApp } from '@/test/render'
import { DataTable, type DataColumn } from './DataTable'

type Row = { id: string; name: string; ports: number }
const rows: Row[] = Array.from({ length: 12 }, (_, i) => ({ id: String(i), name: `sw-${i + 1}`, ports: (i * 7) % 5 }))
const columns: DataColumn<Row>[] = [
  { id: 'name', header: 'Name', sort: (r) => r.name, cell: (r) => r.name },
  { id: 'ports', header: 'Ports', sort: (r) => r.ports, cell: (r) => String(r.ports) },
  { id: 'note', header: 'Note', cell: () => '–' },
]

function Where() {
  const { search } = useLocation()
  return <output data-testid="where">{search}</output>
}

const names = () => within(screen.getByRole('table')).getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)

describe('DataTable', () => {
  it('sorts names naturally, turns on a header click, and keeps it in the address', () => {
    renderWithApp(<><DataTable label="Switches" rows={rows} columns={columns} rowKey={(r) => r.id} defaultSort={{ id: 'name' }} pageSize={5} count={(n) => `${n} switches`} /><Where /></>)
    expect(names()).toEqual(['sw-1', 'sw-2', 'sw-3', 'sw-4', 'sw-5'])   // sw-2 before sw-10
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'ascending')
    expect(screen.getByText('12 switches')).toBeInTheDocument()
    // A column without a sort has no button.
    expect(within(screen.getByRole('columnheader', { name: 'Note' })).queryByRole('button')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Name/ }))
    expect(names()[0]).toBe('sw-12')
    expect(screen.getByTestId('where').textContent).toBe('?sort=-name')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(names()[0]).toBe('sw-7')
    expect(screen.getByTestId('where').textContent).toBe('?sort=-name&page=2')
  })

  it('opens on the view the address names', () => {
    renderWithApp(<DataTable label="Switches" rows={rows} columns={columns} rowKey={(r) => r.id} defaultSort={{ id: 'name' }} pageSize={5} />, '/?sort=ports&page=3')
    expect(screen.getByRole('columnheader', { name: /Ports/ })).toHaveAttribute('aria-sort', 'ascending')
    expect(names()).toHaveLength(2)
  })

  it('keeps its view to itself where several tables share a page', () => {
    renderWithApp(<><DataTable label="Switches" rows={rows} columns={columns} rowKey={(r) => r.id} urlState={false} pageSize={0} /><Where /></>)
    expect(names()).toHaveLength(12)
    fireEvent.click(screen.getByRole('button', { name: /Ports/ }))
    expect(screen.getByTestId('where').textContent).toBe('')
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull()
  })

  it('says so when there is nothing to show', () => {
    renderWithApp(<DataTable label="Switches" rows={[]} columns={columns} rowKey={(r) => r.id} empty="No switches yet." />)
    expect(screen.getByText('No switches yet.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })
})
