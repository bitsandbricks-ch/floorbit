import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FeatureState } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Features from './Features'
import StatsView from './stats/StatsView'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const f = (id: string, over: Partial<FeatureState> = {}): FeatureState => ({ id, on: true, chosen: true, forced_off: false, needs: [], ...over })

describe('Features', () => {
  it('turns a feature off and explains the ones that are off for another reason', async () => {
    const list = [
      f('incidents', { on: false, chosen: false }),
      f('handover', { on: false, needs: ['incidents'] }),
      f('dns', { on: false, chosen: true, forced_off: true }),
      f('cables'),
      f('power'),
    ]
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/features': { features: list, env: 'FLOORBIT_FEATURES_OFF' },
      'PUT /api/settings/features': { features: list.map((x) => (x.id === 'cables' ? { ...x, on: false, chosen: false } : x)), env: 'FLOORBIT_FEATURES_OFF' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Features />)
    expect(await screen.findByText('Off while Incidents is off.')).toBeInTheDocument()
    expect(screen.getByText(/Turned off on the server \(FLOORBIT_FEATURES_OFF\)/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'DNS analytics' })).toBeDisabled()
    // Electrics is switched with its capability, so not here twice.
    expect(screen.queryByRole('switch', { name: 'Electrics' })).toBeNull()
    fireEvent.click(screen.getByRole('switch', { name: 'Cables and patching' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT' && JSON.stringify(c.body) === '{"cables":false}')).toBe(true))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Cables and patching' })).not.toBeChecked())
  })

  it('switches a capability as a whole and says what it still needs', async () => {
    const cap = (state: string) => ({ capabilities: [
      { id: 'captive_note', state, forced_off: false,
        parts: [{ kind: 'setting', id: 'integrations.captive_enabled', on: true }, { kind: 'plugin', id: 'captive-note', on: state === 'on' }],
        needs: [{ id: 'cap.checkin', ok: true, href: '#cap-checkin' }, { id: 'agentConnected', ok: false, href: '/settings/agents' },
          { id: 'dhcp114', ok: null, href: null }] },
    ] })
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/features': { features: [], env: 'FLOORBIT_FEATURES_OFF' },
      'GET /api/settings/capabilities': cap('partly'),
      'PUT /api/settings/capabilities/captive_note': cap('on'),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Features />)
    expect(await screen.findByText('Some parts are off: its plugin. Switch it on to turn them all on.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'A local agent connected' })).toHaveAttribute('href', '/settings/agents')
    expect(screen.getByText("Option 114 in the event's DHCP, pointing at the agent")).toBeInTheDocument()
    const sw = screen.getByRole('switch', { name: 'Check-in note on phones' })
    expect(sw).not.toBeChecked()
    fireEvent.click(sw)
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ on: true }))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Check-in note on phones' })).toBeChecked())
  })

  it('hides the links of features that are off', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/features': { off: ['replay'] },
      'GET /api/stats': { series: [], peak: null, uplinks: [], seats: { online: 0, total: 0 }, top: [], last_poll: null },
    }).fn)
    renderWithApp(<StatsView expanded />)
    expect(await screen.findByRole('link', { name: /Event report/ })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('link', { name: /Replay/ })).not.toBeInTheDocument())
  })
})
