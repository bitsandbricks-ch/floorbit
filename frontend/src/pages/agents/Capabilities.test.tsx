import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { Capabilities } from './Capabilities'

describe('Capabilities', () => {
  it('lists what the agent does and what it collects, with the fallback for each missing one', () => {
    renderWithApp(<Capabilities have={['lease', 'key_roll', 'syslog', 'rest']} />)
    const agent = screen.getByRole('list', { name: 'The agent' })
    expect(within(agent).getByText('Fetches a new key itself when you roll it.')).toBeInTheDocument()
    expect(within(agent).getByText('Its lines have no ids: in a group the same line can show twice.')).toBeInTheDocument()
    const collects = screen.getByRole('list', { name: 'What it collects' })
    expect(within(collects).getByText('Relays the devices\' syslog to Floorbit.')).toBeInTheDocument()
    expect(within(collects).getByText('Polls the devices\' own APIs.')).toBeInTheDocument()
    expect(within(collects).getByText('No Telegraf on this agent, or telemetry is off: no SNMP polling.')).toBeInTheDocument()
    expect(within(collects).getByText('Check-in uses the polled ARP and MAC tables only.')).toBeInTheDocument()
  })
})
