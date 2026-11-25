import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import type { FlowsData } from '@/api/types'
import { trendOf } from './format'
import { TrafficServices } from './TrafficServices'

const HOUR = 3600
const NOW = 1_800_000_000
const H = Math.floor(NOW / HOUR) * HOUR
const data = {
  updated: NOW, min_seats: 5, other_services: 1000,
  services: [
    { name: 'Steam', category: 'gaming', bytes: 9_000_000_000, seats: 40, down: 8_000_000_000, up: 1_000_000_000,
      trend: { [String(H - HOUR)]: 4_000_000_000, [String(H)]: 5_000_000_000 }, areas: { A: 6_000_000_000, B: 2_000_000_000 } },
    // An older agent: no down, up, trend or blocks.
    { name: 'Twitch', category: 'streaming', bytes: 3_000_000_000, seats: 12 },
  ],
} as unknown as FlowsData

describe('TrafficServices', () => {
  it('lists each application with seats, down and up', () => {
    renderWithApp(<TrafficServices data={data} />)
    const steam = screen.getByText('Steam').closest('tr')!
    expect(steam).toHaveTextContent('40')
    expect(steam).toHaveTextContent('8.0 GB')
    expect(steam).toHaveTextContent('1.0 GB')
    expect(screen.getByText('Twitch').closest('tr')).toHaveTextContent('3.0 GB')
  })

  it('opens an application with its bytes per block and per hour', () => {
    renderWithApp(<TrafficServices data={data} />)
    fireEvent.click(screen.getByText('Steam'))
    const panel = screen.getByRole('dialog')
    expect(within(panel).getByText('A')).toBeInTheDocument()
    expect(within(panel).getByText('Blocks with fewer seats')).toBeInTheDocument()
  })

  it('fills the hours a service had nothing with 0', () => {
    const steam = data.services![0]
    expect(trendOf(steam, NOW).map((p) => p.bytes)).toEqual([0, 0, 0, 0, 4_000_000_000, 5_000_000_000])
  })
})
