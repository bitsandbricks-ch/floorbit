import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { DiskBudget } from './AgentDisk'

const GB = 1e9

describe('DiskBudget', () => {
  it('shows the budget and each kind, biggest first, with the hours it reaches back', () => {
    renderWithApp(<DiskBudget disk={{
      auto: true, budget: 50 * GB, used: 20 * GB,
      kinds: { buffer: { bytes: 2 * GB, hours: 1 }, flows: { bytes: 18 * GB, hours: 31.5, dropped: 3 } },
    }} />)
    expect(screen.getByText('Disk budget (automatic)')).toBeInTheDocument()
    expect(screen.getByText('20.0 GB of 50.0 GB')).toBeInTheDocument()
    const labels = screen.getAllByText(/Raw flows|Buffer while/).map((e) => e.textContent)
    expect(labels).toEqual(['Raw flows', 'Buffer while Floorbit is away'])
    expect(screen.getByText(/18.0 GB, 31.5 hours back/)).toBeInTheDocument()
    expect(screen.getByText(/3 old files overwritten/)).toBeInTheDocument()
  })

  it('shows nothing for an agent that does not report its disk', () => {
    renderWithApp(<DiskBudget />)
    expect(screen.queryByText(/Disk budget/)).toBeNull()
  })
})
