import { fireEvent, screen } from '@testing-library/react'
import i18n from 'i18next'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import SeatHelp, { type SeatHelpState } from './SeatHelp'
import { runSpeedtest } from './seatSpeed'

vi.mock('./seatSpeed', () => ({ runSpeedtest: vi.fn() }))

afterEach(() => { vi.unstubAllGlobals(); vi.mocked(runSpeedtest).mockReset(); void i18n.changeLanguage('en') })

const page = <Routes><Route path="/help/:seat" element={<SeatHelp />} /></Routes>
const API = '/api/helpdesk/seats/A-1?k=abc'
const calm: SeatHelpState = { seat: 'A-1', problems: ['no-internet', 'slow', 'power', 'other'], outage: null, status_url: null,
  back_up: null, report: null, ahead: 0 }

describe('SeatHelp', () => {
  it('reports a problem with one tap', async () => {
    const fake = fakeFetch({ [`GET ${API}`]: calm, [`POST ${API}`]: { state: 'thanks' } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(page, '/help/a-1?k=abc')
    expect(await screen.findByRole('button', { name: 'No power' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Help at seat A-1' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Slow or dropping connection' }))
    expect(await screen.findByText('Thanks, we know. Someone from the team will come to seat A-1.')).toBeInTheDocument()
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ problem: 'slow' })
  })

  it('says where an open report stands and offers "it works again"', async () => {
    const fake = fakeFetch({ [`GET ${API}`]: { ...calm, report: 'open', ahead: 2, outage: 7, status_url: '/status' },
      [`POST ${API}`]: { state: 'ok' } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(page, '/help/A-1?k=abc')
    expect(await screen.findByText(/has been down for 7 min/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Updates on the network status page' })).toHaveAttribute('href', '/status')
    expect(screen.getByText(/2 reports are ahead of yours/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'It works again' }))
    expect(await screen.findByText(/it works again at seat A-1/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Test your connection' })).toBeNull()
  })

  it('says when the link is not valid or it is busy', async () => {
    vi.stubGlobal('fetch', fakeFetch({ [`GET ${API}`]: () => ({ status: 404, body: { code: 'invalid' } }) }).fn)
    renderWithApp(page, '/help/A-1?k=abc')
    expect(await screen.findByRole('alert')).toHaveTextContent('This help link is not valid.')
    expect(screen.queryByRole('button', { name: 'Start the test' })).toBeNull()
  })

  it('runs the speed test and shows the figures', async () => {
    vi.stubGlobal('fetch', fakeFetch({ [`GET ${API}`]: calm }).fn)
    vi.mocked(runSpeedtest).mockImplementation(async (_seat, _k, show) => {
      show('ping', 1.234); show('down', 512.4); show('up', 88.25)
      return { down_mbps: 512.4, up_mbps: 88.25, ping_ms: 1.234, jitter_ms: 0.2 }
    })
    renderWithApp(page, '/help/A-1?k=abc')
    fireEvent.click(await screen.findByRole('button', { name: 'Start the test' }))
    expect(await screen.findByText('Saved for seat A-1. The team sees it with your report.')).toBeInTheDocument()
    expect(runSpeedtest).toHaveBeenCalledWith('A-1', 'abc', expect.any(Function))
    expect(screen.getByText('512')).toBeInTheDocument()
    expect(screen.getByText('88.3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Test again' })).toBeInTheDocument()
  })

  it('speaks German', async () => {
    await i18n.changeLanguage('de-CH')
    vi.stubGlobal('fetch', fakeFetch({ [`GET ${API}`]: calm }).fn)
    renderWithApp(page, '/help/A-1?k=abc')
    expect(await screen.findByRole('button', { name: 'Kein Strom' })).toBeInTheDocument()
  })
})
