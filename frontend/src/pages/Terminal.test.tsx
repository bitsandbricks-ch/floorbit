import { fireEvent, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TerminalInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import TerminalPage from './Terminal'

// jsdom has no canvas: a plain element stands in for xterm.js, with a button that "types".
vi.mock('./terminal/TerminalView', () => ({
  TerminalView: ({ onReady, onData }: { onReady: (h: { write: (d: string) => void; focus: () => void }) => void; onData: (d: string) => void }) => {
    useEffect(() => {
      onReady({ write: (d) => { document.getElementById('screen')!.textContent += d }, focus: () => undefined })
    }, [onReady])
    return (
      <div>
        <pre id="screen" data-testid="screen" />
        <button type="button" onClick={() => onData('show version\r')}>type</button>
      </div>
    )
  },
}))

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'lead', permissions: ['terminal.open'] } }
const info = (over: Partial<TerminalInfo> = {}): TerminalInfo => ({
  available: true, plugin: 'SSH port actions', needs_login: true, switches: ['sw-a-01', 'sw-a-02'], sessions: [],
  idle_minutes: 10, max_minutes: 60, ...over,
})

describe('Terminal', () => {
  it('opens a terminal with the login, shows the output and sends what is typed', async () => {
    let typed = false
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/terminal': info(),
      'POST /api/terminal': () => ({ status: 201, body: { id: 't1', switch: 'sw-a-01' } }),
      'GET /api/terminal/t1/output?after=0': () => ({ body: { data: 'sw-a-01#', next: 8, skipped: 0, closed: null } }),
      // Closes once something was typed, like "exit".
      'GET /api/terminal/t1/output?after=8': () => ({ body: { data: '', next: 8, skipped: 0, closed: typed ? 'The switch closed the connection.' : null } }),
      'POST /api/terminal/t1/input': () => {
        typed = true
        return { body: { ok: true } }
      },
      'POST /api/terminal/t1/resize': { ok: true },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<TerminalPage />, '/terminal?switch=sw-a-01')
    const open = await screen.findByRole('button', { name: 'Open terminal' })
    expect(open).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Your switch username'), { target: { value: 'kim' } })
    fireEvent.change(screen.getByLabelText('Your switch password'), { target: { value: 'pw-1' } })
    fireEvent.click(open)
    await waitFor(() => expect(screen.getByTestId('screen')).toHaveTextContent('sw-a-01#'))
    expect(fake.calls.find((c) => c.method === 'POST' && c.path === '/api/terminal')?.body).toEqual({
      switch: 'sw-a-01', cols: 120, rows: 32, username: 'kim', password: 'pw-1' })
    fireEvent.click(screen.getByRole('button', { name: 'type' }))
    await waitFor(() => expect(fake.calls.find((c) => c.path === '/api/terminal/t1/input')?.body).toEqual({ data: 'show version\r' }))
    expect(await screen.findByText('The switch closed the connection.')).toBeInTheDocument()
  })

  it('says when no plugin can open one', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/terminal': info({ available: false }) }).fn)
    renderWithApp(<TerminalPage />)
    expect(await screen.findByText(/No plugin that can open a switch terminal/)).toBeInTheDocument()
  })
})
