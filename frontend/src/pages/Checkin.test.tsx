import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CheckinInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Checkin from './Checkin'

afterEach(() => vi.unstubAllGlobals())

const info = (over: Partial<CheckinInfo> = {}): CheckinInfo => ({ open: true, opens_at: null, ip: '192.0.2.44', checkin: null, ...over })

describe('Checkin', () => {
  it('checks in and shows the seat big', async () => {
    let done = false
    const fake = fakeFetch({
      'GET /api/checkin/info': () => ({ body: info(done ? { checkin: { seat: 'D-22', username: 'Frag0r' } } : {}) }),
      'POST /api/checkin': () => { done = true; return { body: { ok: true, seat: 'D-22', username: 'Frag0r' } } },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Checkin />, '/checkin')
    fireEvent.change(await screen.findByLabelText(/Seat number/), { target: { value: 'd-22 ' } })
    fireEvent.change(screen.getByLabelText(/Your nickname/), { target: { value: 'Frag0r' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByRole('heading', { name: 'Thanks, Frag0r!' })).toBeInTheDocument()
    expect(screen.getByText('D-22')).toBeInTheDocument()
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ seat: 'd-22', username: 'Frag0r' })
    expect(screen.getByText('Your IP: 192.0.2.44')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Wrong seat? Change it' }))
    expect(screen.getByLabelText(/Seat number/)).toHaveValue('D-22')
  })

  it('says what went wrong', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/checkin/info': info(),
      'POST /api/checkin': () => ({ status: 400, body: { ok: false, error: 'No seat D-99 on the floor plan.' } }),
    }).fn)
    renderWithApp(<Checkin />, '/checkin')
    fireEvent.change(await screen.findByLabelText(/Seat number/), { target: { value: 'D-99' } })
    fireEvent.change(screen.getByLabelText(/Your nickname/), { target: { value: 'Frag0r' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No seat D-99 on the floor plan.')
  })

  it('says when it is closed and when it opens', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': info({ open: false, opens_at: 1_900_000_000, ip: null }) }).fn)
    renderWithApp(<Checkin />, '/checkin')
    expect(await screen.findByRole('heading', { name: "Check-in isn't open yet" })).toBeInTheDocument()
    expect(screen.getByText(/^It opens /)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Seat number/)).not.toBeInTheDocument()
  })
})
