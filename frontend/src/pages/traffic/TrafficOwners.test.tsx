import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import type { FlowsData } from '@/api/types'
import { TrafficOwners } from './TrafficOwners'

const NOW = 1_800_000_000

describe('TrafficOwners', () => {
  it('lists each owner with its AS number, seats, down and up', () => {
    const data = {
      updated: NOW, min_seats: 5, other_owners: 2_000_000_000, owners_list: { updated: Date.now() / 1000 - 3600, ranges: 400_000 },
      owners: [{ asn: 64496, name: 'Example CDN', bytes: 9_000_000_000, down: 8_000_000_000, up: 1_000_000_000, seats: 40 }],
    } as unknown as FlowsData
    renderWithApp(<TrafficOwners data={data} />)
    const row = screen.getByText('Example CDN').closest('tr')!
    expect(row).toHaveTextContent('AS64496')
    expect(row).toHaveTextContent('40')
    expect(row).toHaveTextContent('8.0 GB')
    expect(screen.getByText(/2\.0 GB went to owners fewer seats used/)).toBeInTheDocument()
    expect(screen.getByText(/iptoasn\.com \(public domain\), fetched/)).toBeInTheDocument()
  })

  it('says when the agent has no owner list yet', () => {
    renderWithApp(<TrafficOwners data={{ updated: NOW, owners: [], owners_list: {} } as unknown as FlowsData} />)
    expect(screen.getByText(/fetches the list of network owners once a day/)).toBeInTheDocument()
  })
})
