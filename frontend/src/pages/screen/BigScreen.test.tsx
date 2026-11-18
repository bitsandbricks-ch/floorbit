import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import BigScreen, { type ScreenSetup } from './BigScreen'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

const setup: ScreenSetup = {
  views: [{ id: 'floor', url: '/dashboards/kiosk' }, { id: 'heat', url: '/plan?screen=1' }, { id: 'stats', url: '/stats?screen=1' }],
  every: 10,
  qr: { url: 'https://floor.example.com/find', image: 'data:image/svg+xml,<svg/>' },
}

function frames(container: HTMLElement) {
  return [...container.querySelectorAll('iframe')].map((f) => [f.title, f.getAttribute('src'), f.classList.contains('is-on')])
}

describe('BigScreen', () => {
  it('shows one view, warms up the next, and steps by hand and by key', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/screen?views=floor,heat,stats': setup }).fn)
    const { container } = renderWithApp(<BigScreen />, '/screen?views=floor,heat,stats')
    expect(await screen.findByText('Floor plan · 1 of 3')).toBeInTheDocument()
    expect(frames(container)).toEqual([
      ['Floor plan', '/dashboards/kiosk', true], ['Seat traffic', '/plan?screen=1', false], ['Stats', null, false]])
    fireEvent.click(screen.getByRole('button', { name: 'Next view' }))
    expect(frames(container)[1][2]).toBe(true)
    expect(frames(container)[2][1]).toBe('/stats?screen=1')   // the next one loads ahead
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('Floor plan · 1 of 3')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('Stats · 3 of 3')).toBeInTheDocument()
  })

  it('moves on by itself until paused', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/screen': setup }).fn)
    renderWithApp(<BigScreen />, '/screen')
    await screen.findByText('Floor plan · 1 of 3')
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(screen.getByText('Seat traffic · 2 of 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    act(() => { vi.advanceTimersByTime(30_000) })
    expect(screen.getByText('Seat traffic · 2 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('asks guests in both languages to find their seat', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/screen': { ...setup, views: setup.views.slice(0, 1) } }).fn)
    renderWithApp(<BigScreen />, '/screen')
    const qr = await screen.findByRole('complementary', { name: 'Find your seat' })
    expect(qr).toHaveTextContent('Finde deinen Platz')
    expect(qr).toHaveTextContent('https://floor.example.com/find')
    expect(screen.queryByRole('button', { name: 'Next view' })).toBeNull()   // one view: nothing to step
  })
})
