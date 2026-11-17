import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import SidebarSections from './SidebarSections'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }

describe('SidebarSections', () => {
  it('adds a section with an address link and saves the whole list', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/sidebar': { sections: [], icons: ['dashboard', 'star'] },
      'PUT /api/settings/sidebar': { sections: [], icons: ['dashboard', 'star'] },
      'GET /api/options/dashboards': { options: [{ value: 'kiosk', label: 'Kiosk' }] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SidebarSections />)
    expect(await screen.findByText('No sections of your own yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Add section' }))
    fireEvent.change(screen.getByRole('textbox', { name: /^Name$/ }), { target: { value: 'Main hall' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Star' }))
    fireEvent.click(screen.getByText('Address'))
    fireEvent.change(await screen.findByRole('textbox', { name: /Address/ }), { target: { value: 'https://example.com' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Name in the sidebar/ }), { target: { value: 'Grafana' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const sent = api.calls.find((c) => c.method === 'PUT')?.body as { sections: { name: string; icon: string; links: unknown[] }[] } | undefined
      expect(sent?.sections).toEqual([{ id: '', name: 'Main hall', icon: 'star', links: [{ kind: 'url', href: 'https://example.com', label: 'Grafana' }] }])
    })
  })
})
