import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ConfigCopy, ConfigOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Configs from './Configs'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'lead', permissions: ['configs.read'] } }
const copy = (id: string, at: number): ConfigCopy => ({ id, at, by: 'kim', sha: id, lines: 120 })
const overview = (over: Partial<ConfigOverview> = {}): ConfigOverview => ({
  available: true, plugin: 'SSH port actions', needs_login: false, keep: 50, max_switches: 20,
  switches: [
    { switch: 'sw-a-01', copies: 2, last: copy('b', 1_800_000_600), checked: { at: 1_800_000_600, by: 'kim' },
      baseline: copy('a', 1_800_000_000), changed: true },
    { switch: 'sw-a-02', copies: 0, last: null, checked: null, baseline: null, changed: false },
  ],
  ...over,
})

describe('Configs', () => {
  it('lists the switches with what changed and backs up the ones without a copy', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/configs': overview(),
      'POST /api/configs/backup': { results: [{ switch: 'sw-a-02', ok: true, error: null, changed: true, copy: copy('c', 1) }] },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Configs />, '/configs')
    expect(await screen.findByText('Changed')).toBeInTheDocument()
    expect(screen.getByText('No copy yet')).toBeInTheDocument()
    expect(screen.getByText('1 of 2 changed since the baseline')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Without a copy' }))
    fireEvent.click(screen.getByRole('button', { name: 'Back up 1 switch' }))
    expect(await screen.findByText('1 switch backed up, 1 changed.')).toBeInTheDocument()
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ switches: ['sw-a-02'] })
  })

  it('shows a switch history and the diff from the baseline', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me, 'GET /api/configs': overview(),
      'GET /api/configs/sw-a-01': { switch: 'sw-a-01', copies: [copy('b', 1_800_000_600), copy('a', 1_800_000_000)], baseline: 'a', checked: null },
      'GET /api/configs/sw-a-01/diff?from=&to=': { from: copy('a', 1_800_000_000), to: copy('b', 1_800_000_600), added: 1, removed: 0,
        lines: ['--- a', '+++ b', '@@ -1,2 +1,3 @@', ' interface Gi1/0/3', '+ shutdown', ' !'] },
    }).fn)
    renderWithApp(<Configs />, '/configs')
    fireEvent.click(await screen.findByRole('button', { name: 'sw-a-01' }))
    expect(await screen.findByText('+ shutdown')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('Baseline').length).toBeGreaterThan(0))
  })
})
