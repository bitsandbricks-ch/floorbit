import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { WifiHistory } from './WifiHistory'

afterEach(() => vi.unstubAllGlobals())

const now = Math.floor(Date.now() / 1000)

describe('WifiHistory', () => {
  it('draws the clients of the streaming controllers and changes the range', async () => {
    const fake = fakeFetch({
      'GET /api/wifi/history?hours=6': { controllers: ['wlc-01'], hours: 6, points: [[now - 120, 52], [now - 60, 61]] },
      'GET /api/wifi/history?hours=24': { controllers: ['wlc-01'], hours: 24, points: [] },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<WifiHistory />)
    expect(await screen.findByRole('img', { name: 'Clients over time' })).toBeInTheDocument()
    expect(screen.getByText(/max 61/)).toBeInTheDocument()
    expect(screen.getByText('From the controllers that stream to Telemetry: wlc-01.')).toBeInTheDocument()
    await userEvent.click(screen.getByText('24 hours'))
    expect(await screen.findByText(/No history yet/)).toBeInTheDocument()
  })
})
