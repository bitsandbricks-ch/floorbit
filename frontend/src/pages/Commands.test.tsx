import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CommandInfo, CommandRun } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Commands from './Commands'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'lead', permissions: ['ports.act', 'commands.change'] } }
const info = (over: Partial<CommandInfo> = {}): CommandInfo => ({
  available: true, plugin: 'SSH port actions', needs_login: true, platform: 'cisco_ios', may_change: true, may_edit: false,
  switches: ['sw-a-01', 'sw-a-02'], max_switches: 20,
  templates: [
    { id: 'version', kind: 'show', label: 'Software version', commands: ['show version'], builtin: true, needs_port: false },
    { id: 'clear_counters', kind: 'change', label: 'Clear port counters', commands: ['clear counters {port}'], builtin: true, needs_port: true },
  ],
  ...over,
})
const answer: CommandRun = {
  template: 'version', label: 'Software version', kind: 'show', port: null, commands: ['show version'],
  results: [
    { switch: 'sw-a-01', ok: true, output: 'Example IOS 17.9', error: null, ms: 800 },
    { switch: 'sw-a-02', ok: false, output: '', error: 'sw-a-02 refused the login.', ms: 300 },
  ],
}

describe('Commands', () => {
  it('runs a show command on the switches from the link and shows the answers side by side', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/commands': info(), 'POST /api/commands/run': answer })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Commands />, '/commands?switch=sw-a-01&switch=sw-a-02')
    expect(await screen.findByText('show version')).toBeInTheDocument()
    const run = screen.getByRole('button', { name: 'Run on 2 switches' })
    expect(run).toBeDisabled()                                   // no login yet
    fireEvent.change(screen.getByLabelText('Your switch username'), { target: { value: 'kim' } })
    fireEvent.change(screen.getByLabelText('Your switch password'), { target: { value: 'pw-123' } })
    fireEvent.click(run)
    expect(await screen.findByText('Example IOS 17.9')).toBeInTheDocument()
    expect(screen.getByText('sw-a-02 refused the login.')).toBeInTheDocument()
    expect(screen.getByText('1 of 2 failed')).toBeInTheDocument()
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({
      template: 'version', switches: ['sw-a-01', 'sw-a-02'], username: 'kim', password: 'pw-123' })
    // The password is gone from the form after the run.
    expect(screen.getByLabelText('Your switch password')).toHaveValue('')
  })

  it('asks a second time before a change command', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/commands': info({ needs_login: false }),
      'POST /api/commands/run': { ...answer, template: 'clear_counters', kind: 'change', results: [answer.results[0]] } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Commands />, '/commands?template=clear_counters&switch=sw-a-01&port=Gi1/0/3')
    expect(await screen.findByText('clear counters Gi1/0/3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run on 1 switch' }))
    expect(await screen.findByText('Run a command that changes something?')).toBeInTheDocument()
    expect(fake.calls.some((c) => c.method === 'POST')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Run it' }))
    await waitFor(() => expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({
      template: 'clear_counters', switches: ['sw-a-01'], port: 'Gi1/0/3', confirm: true }))
  })

  it('says when no plugin can run commands', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/commands': info({ available: false }) }).fn)
    renderWithApp(<Commands />)
    expect(await screen.findByText(/No plugin that can run switch commands/)).toBeInTheDocument()
  })
})
