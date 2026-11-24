import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mergeSteps, type TraceStep } from '@/api/seatWalkTrace'
import { renderWithApp } from '@/test/render'
import { FlowStrip, LaptopStrip, TraceConsole } from './Trace'

const at = 1_790_000_000_000
const step = (n: number, code: string, state: TraceStep['state'], args: TraceStep['args'] = {}, ms?: number): TraceStep =>
  ({ at: at + n, code, state, args, ...(ms !== undefined ? { ms } : {}) })

// A laptop at A-15: the tables are old, the row's switch still names the last seat, the block has it.
const steps: TraceStep[] = [
  step(0, 'hello', 'ok', { agent: 'Hall agent', ip: '192.0.2.57' }),
  step(1, 'macReused', 'ok', { mac: '02:00:00:00:00:10' }),
  step(2, 'monitoring', 'no', { result: 'none' }, 12),
  step(3, 'snmpAsk', 'run', { vlan: 110, row: ['sw-a1'], block: ['sw-a2'], others: 12 }),
  step(4, 'snmpSwitch', 'skip', { switch: 'sw-a1', group: 'row', result: 'uplink', port: 'Gi1/0/48' }, 210),
  step(5, 'snmpSwitch', 'ok', { switch: 'sw-a2', group: 'block', result: 'found', port: 'Gi1/0/15' }, 190),
  step(6, 'found', 'ok', { switch: 'sw-a2', port: 'Gi1/0/15', how: 'snmp' }, 450),
]

describe('seat walk trace', () => {
  it('words every step, with the group each switch was asked in', () => {
    renderWithApp(<TraceConsole steps={steps} running={false} />)
    const log = screen.getByRole('log', { name: 'What Floorbit is doing' })
    expect(within(log).getByText('Hall agent saw the laptop at 192.0.2.57')).toBeInTheDocument()
    expect(within(log).getByText("sw-a1 (row's switch): only on uplink Gi1/0/48, skipped")).toBeInTheDocument()
    expect(within(log).getByText('sw-a2 (block): on Gi1/0/15')).toBeInTheDocument()
    expect(within(log).getByText('210 ms')).toBeInTheDocument()
  })

  it('says the laptop is hidden when the live bus left its address out', () => {
    renderWithApp(<TraceConsole steps={[step(0, 'hello', 'ok', { agent: 'Hall agent' })]} running />)
    expect(screen.getByText('Hall agent saw the laptop at (hidden)')).toBeInTheDocument()
  })

  it('shows where the lookup is: the block found it after the row', () => {
    renderWithApp(<FlowStrip steps={steps} running={false} seat="A-15" />)
    const flow = screen.getByRole('list', { name: 'Where the lookup is' })
    const items = within(flow).getAllByRole('listitem')
    const state = (label: string) => items.find((i) => i.textContent?.startsWith(label))?.querySelector('[data-state]')?.getAttribute('data-state')
    expect(state("Row's switch")).toBe('no')
    expect(state('Block')).toBe('done')
    expect(state('A-15')).toBe('done')
    expect(within(flow).getByText('sw-a2 Gi1/0/15')).toBeInTheDocument()
  })

  it('marks the row as being asked while the agent has not answered yet', () => {
    renderWithApp(<FlowStrip steps={steps.slice(0, 4)} running seat="A-15" />)
    const now = screen.getAllByRole('listitem').find((i) => i.querySelector('[data-state="now"]'))
    expect(now?.textContent).toContain("Row's switch")
  })

  it('shows the agent address to open and the laptop it looks for', () => {
    renderWithApp(<LaptopStrip agentUrl="https://checkin.example.com:9443" ip="192.0.2.57" mac="02:00:00:00:00:10" agent="Hall agent" />)
    expect(screen.getByText('https://checkin.example.com:9443')).toBeInTheDocument()
    expect(screen.getByText('192.0.2.57 · 02:00:00:00:00:10')).toBeInTheDocument()
    expect(screen.getByText('Hall agent')).toBeInTheDocument()
  })

  it('keeps each step once when the live bus and the answer both bring it', () => {
    const merged = mergeSteps(steps.slice(0, 3), steps)
    expect(merged).toHaveLength(steps.length)
    expect(merged.map((s) => s.code)).toEqual(steps.map((s) => s.code))
  })
})
