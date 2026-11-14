import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatMapList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import SeatMapping from './SeatMapping'
import { matches } from './seatmap/model'

afterEach(() => vi.unstubAllGlobals())

const list: SeatMapList = {
  seats: [
    {
      seat: 'A-1',
      ip: '192.0.2.99',
      mac: '',
      nick: 'player1',
      from: { ip: 'manual', nick: 'checkin' },
      manual: { seat: 'A-1', ip: '192.0.2.99', mac: '', nick: '', note: 'console', updated_at: null, updated_by: null },
      sources: ['manual', 'checkin'],
    },
    { seat: 'A-2', ip: '192.0.2.2', mac: 'aa:bb:cc:dd:ee:02', nick: 'player2', from: { ip: 'checkin', mac: 'checkin', nick: 'checkin' }, manual: null, sources: ['checkin'] },
  ],
  sources: ['manual', 'checkin'],
  errors: {},
  labels: { manual: 'Entered by hand', checkin: 'Seat check-in page' },
}
const me = { 'GET /api/auth/me': { enabled: true, user: { username: 'ed', display_name: 'Ed', role: 'editor' } } }

describe('matches', () => {
  it('finds by seat, nick, IP and MAC, and can show only hand entries', () => {
    expect(matches(list.seats[1], 'ee:02', false)).toBe(true)
    expect(matches(list.seats[1], '', true)).toBe(false)
    expect(matches(list.seats[0], 'console', true)).toBe(true)
  })
})

describe('Seat mapping page', () => {
  it('marks hand-entered fields and lists the sources', async () => {
    vi.stubGlobal('fetch', fakeFetch({ ...me, 'GET /api/seat-map': list }).fn)
    renderWithApp(<SeatMapping />)
    const row = (await screen.findByRole('button', { name: 'A-1' })).closest('tr')!
    expect(within(row).getAllByLabelText('By hand')).toHaveLength(1)   // only the IP
    expect(within(row).getByText('Seat check-in page')).toBeInTheDocument()
    expect(within(row).getByText('console')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute('href', '/api/seat-map.csv')
  })

  it('shows what an empty field falls back to and saves the hand entry', async () => {
    const api = fakeFetch({ ...me, 'GET /api/seat-map': list, 'PUT /api/seat-map/A-2': { seat: 'A-2', entry: {} } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatMapping />)
    fireEvent.click(await screen.findByRole('button', { name: 'A-2' }))
    expect(await screen.findByText('Without a hand entry: 192.0.2.2 (from Seat check-in page)')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('MAC'), { target: { value: 'AA-BB-CC-00-00-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ ip: '', mac: 'AA-BB-CC-00-00-01', nick: '', note: '' }),
    )
  })

  it('checks a CSV before importing and lists the problems', async () => {
    const api = fakeFetch({
      ...me,
      'GET /api/seat-map': list,
      'POST /api/seat-map/import': () => ({ status: 400, body: { error: '1 line(s) have problems; nothing was imported', problems: ['line 2: "x" is not an IP address'] } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatMapping />)
    fireEvent.click(await screen.findByRole('button', { name: 'Import CSV' }))
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['seat,ip\nA-1,x\n'], 'seats.csv', { type: 'text/csv' })] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Check file' }))
    expect(await screen.findByText('line 2: "x" is not an IP address')).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ csv: 'seat,ip\nA-1,x\n', replace: false, dry_run: true })
  })
})
