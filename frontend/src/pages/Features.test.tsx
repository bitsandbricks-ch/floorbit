import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FeatureState } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Features from './Features'
import Stats from './Stats'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const f = (id: string, over: Partial<FeatureState> = {}): FeatureState => ({ id, on: true, chosen: true, forced_off: false, needs: [], ...over })

describe('Features', () => {
  it('turns a feature off and explains the ones that are off for another reason', async () => {
    const list = [
      f('incidents', { on: false, chosen: false }),
      f('handover', { on: false, needs: ['incidents'] }),
      f('traffic', { on: false, chosen: true, forced_off: true }),
      f('power'),
    ]
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/features': { features: list, env: 'FLOORBIT_FEATURES_OFF' },
      'PUT /api/settings/features': { features: list.map((x) => (x.id === 'power' ? { ...x, on: false, chosen: false } : x)), env: 'FLOORBIT_FEATURES_OFF' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Features />)
    expect(await screen.findByText('Off while Incidents is off.')).toBeInTheDocument()
    expect(screen.getByText(/Turned off on the server \(FLOORBIT_FEATURES_OFF\)/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Traffic (NetFlow)' })).toBeDisabled()
    fireEvent.click(screen.getByRole('switch', { name: 'Electrics' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT' && JSON.stringify(c.body) === '{"power":false}')).toBe(true))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Electrics' })).not.toBeChecked())
  })

  it('hides the links of features that are off', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/features': { off: ['replay'] },
      'GET /api/stats': { series: [], peak: null, uplinks: [], seats: { online: 0, total: 0 }, top: [], last_poll: null },
    }).fn)
    renderWithApp(<Stats />)
    expect(await screen.findByRole('link', { name: /Event report/ })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('link', { name: /Replay/ })).not.toBeInTheDocument())
  })
})
