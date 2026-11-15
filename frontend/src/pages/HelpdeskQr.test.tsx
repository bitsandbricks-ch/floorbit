import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import HelpdeskQr from './HelpdeskQr'
import { parseSeats, seatBlock } from './incidents/qrFilter'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['incidents.work', 'incidents.assign'] } }
const seat = (s: string) => ({ seat: s, url: `https://floor.example.com/help/${s}?k=x`, image: 'data:image/svg+xml;base64,' })
const sheet = { seats: ['A-1', 'A-2', 'D-6', 'D-7', 'D-8'].map(seat) }

describe('HelpdeskQr', () => {
  it('splits seats into blocks and reads typed seat numbers', () => {
    expect(seatBlock('D-6')).toBe('D')
    expect(seatBlock('HALL-2-14')).toBe('HALL-2')
    expect(seatBlock('17')).toBe('')
    expect([...parseSeats(' d-6, D-7;d-6  ')]).toEqual(['D-6', 'D-7'])
  })

  it('prints one block or a few seats', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/helpdesk/qr': sheet }).fn)
    renderWithApp(<HelpdeskQr />)
    expect(await screen.findByText('5 codes')).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: /QR code for seat/ })).toHaveLength(5)
    fireEvent.change(screen.getByRole('textbox', { name: 'Only these seats' }), { target: { value: 'd-6, D-8' } })
    expect(screen.getByText('2 of 5 codes')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'QR code for seat D-8' })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'QR code for seat D-7' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Only these seats' }), { target: { value: 'Z-1' } })
    expect(screen.getByText(/No seat matches/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Print' })).toBeDisabled()
  })
})
