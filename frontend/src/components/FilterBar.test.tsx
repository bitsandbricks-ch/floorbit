import { fireEvent, screen } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { FilterBar } from './FilterBar'
import { useFilters } from './useFilters'

function List() {
  const f = useFilters({ state: 'all' })
  const where = useLocation()
  return (
    <>
      <FilterBar state={f} searchLabel="Search" filters={[{ id: 'state', label: 'Show', options: [
        { value: 'all', label: 'All', count: 5 }, { value: 'down', label: 'Down', count: 2 },
      ] }]} />
      <output>{where.search || 'none'}</output>
    </>
  )
}

describe('FilterBar', () => {
  it('keeps search and filters in the address, with counts, and clears them', async () => {
    renderWithApp(<List />, '/list')
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show: All' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Down/ }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Search' }), { target: { value: 'sw' } })
    expect(screen.getByRole('status')).toHaveTextContent('?state=down&q=sw')
    expect(screen.getByRole('button', { name: 'Show: Down' })).toHaveTextContent('2')
    fireEvent.click(await screen.findByText('Clear filters'))
    expect(screen.getByRole('status')).toHaveTextContent('none')
  })

  it('opens on the address it was given', () => {
    renderWithApp(<List />, '/list?state=down')
    expect(screen.getByRole('button', { name: 'Show: Down' })).toBeInTheDocument()
  })
})
