import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Marketplace, { type MarketCatalog, type MarketPlugin } from './Marketplace'

const v = (version: string, extra: Partial<MarketPlugin['versions'][number]> = {}) => ({
  version, date: '2026-11-17', changes: '', withdrawn: '', floorbit: '', compatible: true, why: '', ...extra,
})

const fresh: MarketPlugin = {
  id: 'hallthing', name: 'Hall thing', description: 'Shows the hall.', author: 'BitsAndBricks', homepage: '',
  trust: 'official', source: 'https://plugins.example.com/index.json', builtin: false, installed: null, previous: null,
  error: '', enabled: false, withdrawn: '', update: null, best: '1.1.0', listed: true,
  versions: [v('2.0.0', { compatible: false, floorbit: '>=9' }), v('1.1.0', { changes: 'Faster.' }), v('1.0.0', { withdrawn: 'broken' })],
}

const catalog = (plugins: MarketPlugin[], error = ''): MarketCatalog => ({
  sources: [{ url: 'https://plugins.example.com/index.json', official: true, name: 'Floorbit Marketplace', generated: '', error }],
  plugins,
})

afterEach(() => vi.unstubAllGlobals())

describe('Marketplace', () => {
  it('installs the best version and offers only versions that can run', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'admin', display_name: 'Admin', role: 'admin' } },
      'GET /api/settings/marketplace': catalog([fresh]),
      'POST /api/settings/marketplace/hallthing': { id: 'hallthing', version: '1.1.0' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Marketplace />)
    const card = await screen.findByRole('region', { name: 'Hall thing' })
    expect(within(card).getByText('Official')).toBeInTheDocument()
    expect(within(card).getByText('Faster.')).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Install 1.1.0' }))
    await waitFor(() => expect(within(card).getByRole('status')).toHaveTextContent('Hall thing 1.1.0 is installed'))
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({})
  })

  it('shows updates, rollback and a withdrawn version that runs', async () => {
    const running = { ...fresh, installed: '1.0.0', previous: '0.9.0', withdrawn: 'broken', update: '1.1.0' }
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'admin', display_name: 'Admin', role: 'admin' } },
      'GET /api/settings/marketplace': catalog([running]),
      'POST /api/settings/marketplace/hallthing/rollback': { id: 'hallthing', version: '0.9.0' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Marketplace />)
    const card = await screen.findByRole('region', { name: 'Hall thing' })
    expect(within(card).getByRole('alert')).toHaveTextContent('Version 1.0.0 was withdrawn: broken')
    expect(within(card).getByRole('button', { name: 'Update to 1.1.0' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Remove' })).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Back to 0.9.0' }))
    expect(await screen.findByText('Put Hall thing back to version 0.9.0?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(api.calls.some((c) => c.path.endsWith('/rollback'))).toBe(true))
  })

  it('shows what a plugin may touch before it is installed', async () => {
    const touching: MarketPlugin = {
      ...fresh,
      touches: {
        uses: ['settings', 'actions'], permissions: ['floorplan.edit'], secrets: 2,
        sends: { cache_stats: 'aggregate' }, hall_actions: ['purge'], credentials: ['ssh'],
      },
    }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'admin', display_name: 'Admin', role: 'admin' } },
      'GET /api/settings/marketplace': catalog([touching]),
    }).fn)
    renderWithApp(<Marketplace />)
    const card = await screen.findByRole('region', { name: 'Hall thing' })
    const list = within(card).getByLabelText('What it may touch')
    expect(list).toHaveTextContent('its own settings, buttons that run its code')
    expect(list).toHaveTextContent('Change the floor plan and the inventory, run syncs')
    expect(list).toHaveTextContent('cache_stats (hall-wide numbers)')
    expect(list).toHaveTextContent('purge')
    expect(list).toHaveTextContent('SSH')
    expect(list).toHaveTextContent('2 secret settings (write-only)')
  })

  it('says when the index cannot be trusted', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'admin', display_name: 'Admin', role: 'admin' } },
      'GET /api/settings/marketplace': catalog([], 'bad index signature'),
    }).fn)
    renderWithApp(<Marketplace />)
    expect(await screen.findByRole('alert')).toHaveTextContent('bad index signature')
    expect(screen.getByText('The Marketplace lists no plugins yet.')).toBeInTheDocument()
  })
})
