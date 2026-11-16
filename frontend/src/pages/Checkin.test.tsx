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
    // On a PC: the PIN from the seat card and a nick, never the seat.
    fireEvent.change(await screen.findByLabelText(/PIN from your seat card/), { target: { value: 'k7m-2x ' } })
    fireEvent.change(screen.getByLabelText(/Your nickname/), { target: { value: 'Frag0r' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByRole('heading', { name: 'Thanks, Frag0r!' })).toBeInTheDocument()
    expect(screen.getByText('D-22')).toBeInTheDocument()
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ pin: 'K7M2X', username: 'Frag0r' })
    expect(screen.getByText('Your IP: 192.0.2.44')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Wrong seat? Check in again' }))
    expect(screen.getByLabelText(/PIN from your seat card/)).toHaveValue('')
    expect(screen.getByLabelText(/Your nickname/)).toHaveValue('Frag0r')
  })

  it('lets a phone type the seat instead, unless the PIN is required', async () => {
    const fake = fakeFetch({
      'GET /api/checkin/info': info({ suggested_seat: 'D-22' }),
      'POST /api/checkin': () => ({ body: { ok: true, seat: 'D-22', username: 'Frag0r' } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Checkin />, '/checkin')
    expect(await screen.findByText('This PC is at seat D-22.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Type the seat number instead/ }))
    fireEvent.change(screen.getByLabelText(/Seat number/), { target: { value: 'd-22 ' } })
    fireEvent.change(screen.getByLabelText(/Your nickname/), { target: { value: 'Frag0r' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    await screen.findByRole('heading', { name: 'Thanks, Frag0r!' })
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ seat: 'd-22', username: 'Frag0r' })
  })

  it('offers only the PIN when the server asks for it', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': info({ pin_required: true }) }).fn)
    renderWithApp(<Checkin />, '/checkin')
    expect(await screen.findByLabelText(/PIN from your seat card/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Type the seat number instead/ })).not.toBeInTheDocument()
  })

  it('says what went wrong', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/checkin/info': info(),
      'POST /api/checkin': () => ({ status: 403, body: { ok: false, error: 'That PIN is not on any seat card.' } }),
    }).fn)
    renderWithApp(<Checkin />, '/checkin')
    fireEvent.change(await screen.findByLabelText(/PIN from your seat card/), { target: { value: 'ZZZZZ' } })
    fireEvent.change(screen.getByLabelText(/Your nickname/), { target: { value: 'Frag0r' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That PIN is not on any seat card.')
  })

  it('says when it is closed and when it opens', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': info({ open: false, opens_at: 1_900_000_000, ip: null }) }).fn)
    renderWithApp(<Checkin />, '/checkin')
    expect(await screen.findByRole('heading', { name: "Check-in isn't open yet" })).toBeInTheDocument()
    expect(screen.getByText(/^It opens /)).toBeInTheDocument()
    expect(screen.queryByLabelText(/PIN from your seat card/)).not.toBeInTheDocument()
  })
})
