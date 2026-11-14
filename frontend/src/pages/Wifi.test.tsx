import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WifiAp, WifiData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Wifi from './Wifi'
import { channelColor, loadColor } from './wifi/colors'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: false }
const ap = (name: string, px: number, ch5: number, util: number, clients: number, extra: Partial<WifiAp> = {}): WifiAp => ({
  name, model: 'Example AP 6', status: 'up', clients, source: 'UniFi', placed: true, on_plan: true, px, py: 100, busy: false,
  radios: [{ band: '2.4', channel: 1, width: 20, utilization: 30, clients: 2 }, { band: '5', channel: ch5, width: 80, utilization: util, clients: clients - 2 }],
  ...extra,
})
const data: WifiData = {
  aps: [ap('ap-01', 100, 36, 20, 10), ap('ap-02', 300, 36, 85, 50, { busy: true }),
    ap('ap-loose', 0, 52, 5, 3, { placed: false, on_plan: false, px: null, py: null })],
  clients: 63, up: 3, down: [], busy: ['ap-02'],
  overlaps: [{ band: '5', channel: 36, aps: ['ap-01', 'ap-02'] }],
  bands: { '2.4': { clients: 6, radios: 3, utilization: 30 }, '5': { clients: 57, radios: 3, utilization: 37 } },
  sources: ['UniFi'], errors: [], thresholds: { busy: 70, crowded: 40 },
  drawing: { shapes: [], box: '0 0 600 300', cell: 32 }, hall: 'main', halls: [{ id: 'main', name: 'Main hall' }],
}

describe('Wifi', () => {
  it('draws placed APs with their load and lists every AP', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/wifi': data }).fn)
    const { container } = renderWithApp(<Wifi />)
    expect(await screen.findByRole('img', { name: 'Access points on the floor plan, 5 GHz' })).toBeInTheDocument()
    expect(container.querySelectorAll('[data-ap]')).toHaveLength(2)
    expect(container.querySelectorAll('.clash')).toHaveLength(2)
    expect(screen.getByText('85%', { selector: 'text' })).toBeInTheDocument()
    expect(screen.getByText('ap-01 and ap-02: 5 GHz channel 36')).toBeInTheDocument()
    expect(screen.getByText('Not on the plan')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Channels'))
    expect(screen.getAllByText('36', { selector: 'text' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('radio', { name: '2.4 GHz' }))
    expect(screen.getByRole('img', { name: 'Access points on the floor plan, 2.4 GHz' })).toBeInTheDocument()
    expect(container.querySelectorAll('.clash')).toHaveLength(0)
  })

  it('says when no Wi-Fi plugin is on', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/wifi': { ...data, aps: [], sources: [] } }).fn)
    renderWithApp(<Wifi />)
    expect(await screen.findByText(/No Wi-Fi plugin is on/)).toBeInTheDocument()
  })

  it('colours load and channels', () => {
    expect(loadColor(20, 70)).toBe('var(--color-up)')
    expect(loadColor(60, 70)).toBe('var(--color-warn)')
    expect(loadColor(70, 70)).toBe('var(--color-down)')
    expect(loadColor(null, 70)).toBe('var(--color-muted)')
    expect(channelColor(36)).toBe(channelColor(36))
    expect(channelColor(36)).not.toBe(channelColor(40))
  })
})
