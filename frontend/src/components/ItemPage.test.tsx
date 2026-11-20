import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { DangerZone, ItemPage } from './ItemPage'

const back = { href: '/inventory', label: 'Back to the inventory' }

describe('ItemPage', () => {
  it('shows the item once it is there', () => {
    renderWithApp(<ItemPage title="core-01" fallbackTitle="Inventory" back={back} loading={false}><p>ports</p></ItemPage>, '/x')
    expect(screen.getAllByRole('heading', { name: 'core-01' }).length).toBeGreaterThan(0)
    expect(screen.getByText('ports')).toBeInTheDocument()
  })

  it('says when the item is gone and links back to its list', () => {
    renderWithApp(<ItemPage fallbackTitle="Inventory" back={back} loading={false} missing={{ title: 'Not found', desc: 'No such device' }} />, '/x')
    expect(screen.getByText('Not found')).toBeInTheDocument()
    for (const a of screen.getAllByRole('link', { name: 'Back to the inventory' })) expect(a).toHaveAttribute('href', '/inventory')
  })

  it('removes only after asking', async () => {
    const gone = vi.fn()
    renderWithApp(<DangerZone label="Delete" question="Delete core-01?" onConfirm={gone} />, '/x')
    expect(screen.getByRole('heading', { name: 'Remove' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(gone).not.toHaveBeenCalled()
    expect(await screen.findByText('Delete core-01?')).toBeInTheDocument()
  })
})
