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
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ pin: 'K7M2X', username: 'Frag0r', device: expect.any(String) })
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
    expect(fake.calls.find((c) => c.method === 'POST')?.body).toEqual({ seat: 'd-22', username: 'Frag0r', device: expect.any(String) })
  })

  it('asks for the check-in address on the seat PC when the page came from outside the front door', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': info({ ip: null, outside: true, address: 'checkin.lan' }) }).fn)
    renderWithApp(<Checkin />, '/checkin')
    expect(await screen.findByText(/Type checkin.lan on the PC at your seat/)).toBeInTheDocument()
    expect(screen.getByLabelText(/PIN from your seat card/)).toBeInTheDocument()     // the seat and nick still count
    expect(screen.queryByText(/Your IP/)).not.toBeInTheDocument()
  })

  describe('on Floorbit\'s own address', () => {
    const hall = (sure: boolean) => info({ ip: null, outside: true, address: 'checkin.lan', hall: { url: 'http://checkin.lan/checkin?via=abc', sure } })
    afterEach(() => sessionStorage.clear())

    it('goes on to the event network by itself when Floorbit is sure the PC is in the hall', async () => {
      const assign = vi.fn()
      vi.stubGlobal('location', { ...window.location, search: '?pin=K7M2X', assign })
      vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': hall(true) }).fn)
      renderWithApp(<Checkin />, '/checkin')
      expect(await screen.findByText(/Taking you to the check-in on the event network/)).toBeInTheDocument()
      expect(assign).toHaveBeenCalledWith('http://checkin.lan/checkin?via=abc&pin=K7M2X')
    })

    it('offers it otherwise, and the seat and nick still count from here', async () => {
      const assign = vi.fn()
      vi.stubGlobal('location', { ...window.location, assign })
      vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': hall(false) }).fn)
      renderWithApp(<Checkin />, '/checkin')
      fireEvent.click(await screen.findByRole('button', { name: /Continue on the event network/ }))
      expect(assign).toHaveBeenCalledWith('http://checkin.lan/checkin?via=abc')
      expect(screen.getByLabelText(/PIN from your seat card/)).toBeInTheDocument()
    })

    it('doesn\'t go again by itself when the trip just failed', async () => {
      sessionStorage.setItem('fb-checkin-hall-trip', String(Date.now()))
      const assign = vi.fn()
      vi.stubGlobal('location', { ...window.location, assign })
      vi.stubGlobal('fetch', fakeFetch({ 'GET /api/checkin/info': hall(true) }).fn)
      renderWithApp(<Checkin />, '/checkin')
      expect(await screen.findByText(/The event network didn't open/)).toBeInTheDocument()
      expect(assign).not.toHaveBeenCalled()
    })
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
