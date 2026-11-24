import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { NotificationsBell } from './NotificationsBell'

afterEach(() => vi.unstubAllGlobals())

const list = (down: number, look: number): ProblemList => ({
  problems: [], attention: [], counts: { down, warn: look, muted: 0, look, total: down + look },
  mutes: [], quiet_hours: false, checked_at: 0, can_mute: false,
})

describe('The bell counts like the Helpdesk badge (issue #1413)', () => {
  it('shows what is down, and says both counts', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/problems': list(4, 42) }).fn)
    renderWithApp(<NotificationsBell />)
    const bell = await screen.findByRole('button', { name: 'Notifications (4 down · 42 need a look)' })
    expect(bell).toHaveTextContent('4')
    expect(bell).not.toHaveTextContent('46')
  })

  it('shows only a dot when nothing is down', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/problems': list(0, 3) }).fn)
    renderWithApp(<NotificationsBell />)
    const bell = await screen.findByRole('button', { name: 'Notifications (3 need a look)' })
    expect(bell.querySelector('.fb-topbar-dot')).not.toBeNull()
    expect(bell.querySelector('.fb-topbar-count')).toBeNull()
  })
})
