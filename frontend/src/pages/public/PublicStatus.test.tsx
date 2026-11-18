import { act, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import PublicStatus, { type PublicStatusData } from './PublicStatus'

afterEach(() => { vi.unstubAllGlobals(); void i18n.changeLanguage('en') })

const now = Date.now() / 1000
const status = (over: Partial<PublicStatusData> = {}): PublicStatusData => ({
  state: 'operational', since: null, checked_at: now, areas: [], recovered: [], recovered_at: null,
  updates: [], ...over,
})

describe('PublicStatus', () => {
  it('says all is well, with the crew updates', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /status.json': status({
      updates: [{ at: now - 60, text: 'Hall B is back.', state: 'operational', area: 'Hall B' }] }) }).fn)
    renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByText('All systems running')).toBeInTheDocument()
    expect(screen.getByText('Hall B is back.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /feed reader/ })).toBeNull()
  })

  it('names the blocks and rows an outage hits, and what came back', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /status.json': status({
      state: 'degraded', since: now - 120, areas: [{ hall: '', block: 'A', rows: '1-2', seats: 2 }],
      recovered: [{ hall: '', block: 'C', rows: '1', seats: 1 }], recovered_at: now - 300 }) }).fn)
    renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByText('Part of the network is down')).toBeInTheDocument()
    expect(screen.getByText('Seat block A')).toBeInTheDocument()
    expect(screen.getByText('rows 1-2 · 2 seats')).toBeInTheDocument()
    expect(screen.getByText('Back up recently')).toBeInTheDocument()
    expect(screen.getByText('Seat block C')).toBeInTheDocument()
  })

  it('shows maintenance set by the crew, and times in 24 hours', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /status.json': status({ state: 'maintenance', since: now - 600 }) }).fn)
    const { container } = renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByText('Maintenance')).toBeInTheDocument()
    expect(screen.queryByText('Planned maintenance')).toBeNull()
    expect(container.textContent).not.toMatch(/\b(AM|PM)\b/)
  })

  it('escapes what the crew typed', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /status.json': status({ updates: [{ at: now, text: '<b>bold</b>' }] }) }).fn)
    const { container } = renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByText('<b>bold</b>')).toBeInTheDocument()
    expect(container.querySelector('li b')).toBeNull()
  })

  it('says when the page is switched off', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page is switched off.')
  })

  it('speaks German', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /status.json': status({ recovered: [{ block: 'A' }], recovered_at: now }) }).fn)
    renderWithApp(<PublicStatus />, '/status')
    expect(await screen.findByText('Alles läuft')).toBeInTheDocument()
    expect(screen.getByText('Wieder da')).toBeInTheDocument()
  })
})
