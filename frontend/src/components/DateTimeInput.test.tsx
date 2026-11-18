import { fireEvent, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { DateTimeInput } from './DateTimeInput'

function Field({ start = '' }: { start?: string }) {
  const [v, setV] = useState(start)
  return <><DateTimeInput label="Start" value={v} onChange={setV} /><output data-testid="value">{v}</output></>
}

describe('DateTimeInput', () => {
  it('shows the value in 24-hour time, day first', () => {
    renderWithApp(<Field start="2026-11-16T16:00" />)
    expect(screen.getByLabelText('Start')).toHaveValue('16.11.2026 16:00')
  })

  it('reads what people type when they leave the field', () => {
    renderWithApp(<Field />)
    const input = screen.getByLabelText('Start')
    fireEvent.change(input, { target: { value: '14.11.2026 1830' } })
    fireEvent.blur(input)
    expect(screen.getByTestId('value')).toHaveTextContent('2026-11-14T18:30')
    expect(input).toHaveValue('14.11.2026 18:30')
  })

  it('says so when it cannot read a date, and keeps the value', () => {
    renderWithApp(<Field start="2026-11-16T16:00" />)
    const input = screen.getByLabelText('Start')
    fireEvent.change(input, { target: { value: 'tomorrow-ish' } })
    fireEvent.blur(input)
    expect(screen.getByText(/Example: 14.11.2026 18:00/)).toBeInTheDocument()
    expect(screen.getByTestId('value')).toHaveTextContent('2026-11-16T16:00')
  })

  // One pick per test: jsdom keeps Mantine's popover in its closing transition after a re-render,
  // which a real browser doesn't (checked in Chromium on /schedule).
  it('picks a day from the calendar and keeps the time', async () => {
    renderWithApp(<Field start="2026-11-16T16:00" />)
    fireEvent.click(screen.getByRole('button', { name: 'Pick a date and time' }))
    fireEvent.click(await screen.findByRole('button', { name: /21 November 2026|November 21, 2026/ }))
    expect(screen.getByTestId('value')).toHaveTextContent('2026-11-21T16:00')
  })

  it('picks a quick time and keeps the day', async () => {
    renderWithApp(<Field start="2026-11-16T16:00" />)
    fireEvent.click(screen.getByRole('button', { name: 'Pick a date and time' }))
    fireEvent.click(await screen.findByRole('button', { name: '20:00' }))
    expect(screen.getByTestId('value')).toHaveTextContent('2026-11-16T20:00')
  })

  it('emptying the field clears the value', () => {
    renderWithApp(<Field start="2026-11-16T16:00" />)
    const input = screen.getByLabelText('Start')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.blur(input)
    expect(screen.getByTestId('value')).toHaveTextContent(/^$/)
  })
})
