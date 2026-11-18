import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import PluginPage from './PluginPage'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: true, user: { username: 'tech', display_name: 'Tech', role: 'tech' } }
const page = (tiles: unknown[]) => ({ plugin: 'pagething', plugin_name: 'Page thing', icon: 'gamepad', id: 'overview', label: 'Game servers', columns: 2, tiles })
const show = () => renderWithApp(<Routes><Route path="/plugins/:plugin/:page" element={<PluginPage />} /></Routes>, '/plugins/pagething/overview')

describe('Plugin page', () => {
  it('draws the plugin\'s tiles under its own title', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/plugins/pagething/pages/overview': page([
        { plugin: 'pagething', plugin_name: 'Page thing', id: 'players', label: 'Players', size: 'small', refresh: 60, url: '/api/plugins/pagething/widgets/players' },
      ]),
      'GET /api/plugins/pagething/widgets/players': { id: 'players', type: 'stat', value: 312, unit: '', tone: 'ok', sub: 'on 4 servers', link: '' },
    }).fn)
    show()
    expect((await screen.findAllByRole('heading', { name: 'Game servers' })).length).toBeGreaterThan(0)
    expect(screen.getByText('From Page thing')).toBeInTheDocument()
    expect(await screen.findByText('312')).toBeInTheDocument()
  })

  it('says so when the account may see none of its tiles', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plugins/pagething/pages/overview': page([]) }).fn)
    show()
    expect(await screen.findByText(/nothing on this page/i)).toBeInTheDocument()
  })

  it('shows a page that is gone as an error', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/plugins/pagething/pages/overview': () => ({ status: 404, body: { error: 'No such page' } }),
    }).fn)
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('No such page')
  })
})
