import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { LibreNMSAlertsSetup } from './LibreNMSAlertsSetup'

afterEach(() => vi.unstubAllGlobals())

const setup = {
  enabled: true, port: 9530, method: 'POST', content_type: 'application/json', body: '{"state": {{ $alert->state }}}',
  token: 'fbl_example', active: 2,
  agents: [{ id: 'a1', name: 'Hall', connected: true, url: 'https://<agent address>:9530/librenms', address_known: false },
    { id: 'a2', name: 'Spare', connected: true, url: 'http://<agent address>:9530/librenms', address_known: false, status: 'error', problem: 'port 9530 taken' }],
}

describe('LibreNMSAlertsSetup', () => {
  it('shows what to paste only when asked, since it shows the token', async () => {
    const api = fakeFetch({ 'GET /api/alerts/librenms/setup': setup })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<LibreNMSAlertsSetup />)
    expect(screen.queryByText('fbl_example')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show what to paste' }))
    expect(await screen.findByText('fbl_example')).toBeInTheDocument()
    expect(screen.getByText('https://<agent address>:9530/librenms')).toBeInTheDocument()
    expect(screen.getAllByText(/put in the agent's address/)).toHaveLength(2)
    expect(screen.getByText('Not listening on this agent: port 9530 taken')).toBeInTheDocument()
    expect(screen.getByText('2 LibreNMS alerts open right now.')).toBeInTheDocument()
  })
})
