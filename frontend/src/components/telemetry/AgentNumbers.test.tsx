import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { TelemetryAgentNumbersList } from './AgentNumbers'

const base = { id: 'a1', name: 'Hall agent', connected: true, status: 'ok', primary: true, points: 6720, series: 124,
  sent: 69, heard: 1, failing: 0, quiet: 23, refused: 0, bad_lines: 0 }

describe('TelemetryAgentNumbersList', () => {
  it('says whether Telegraf posts and the agent forwards', async () => {
    renderWithApp(<TelemetryAgentNumbersList agents={[base, { ...base, id: 'b', name: 'Old box', quiet: 900, refused: 3 }]} />)
    expect(await screen.findByText('Telegraf posted 23 s ago')).toBeInTheDocument()
    expect(screen.getAllByText(/6,720 points received · 1 devices heard · 124 series · 69 sends to Floorbit/)).toHaveLength(2)
    expect(screen.getByText('nothing from Telegraf lately')).toBeInTheDocument()
    expect(screen.getByText('3 posts refused, 0 lines not understood')).toBeInTheDocument()
  })
})
