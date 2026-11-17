import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { SnapToggles } from './SnapToggles'
import { resetSnapPrefs } from './snap'

afterEach(resetSnapPrefs)

describe('the top bar snap toggles', () => {
  it('turns grid snapping off and keeps it for the next visit, and shows or hides the grid layer', () => {
    const onLayers = vi.fn()
    renderWithApp(<SnapToggles layers={{ on: new Set(['grid']), fade: {} }} onLayers={onLayers} />)
    const snap = screen.getByRole('button', { name: /Snap to the grid/ })
    expect(snap).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(snap)
    expect(snap).toHaveAttribute('aria-pressed', 'false')
    expect(JSON.parse(localStorage.getItem('floorbit-plan-snap')!)).toMatchObject({ grid: false })
    fireEvent.click(screen.getByRole('button', { name: 'Show the grid' }))
    expect([...onLayers.mock.calls[0][0].on]).toEqual([])
  })
})
