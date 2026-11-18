import { act, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { scaled } from '@/lib/units'
import PublicWall, { type WallFacts } from './PublicWall'

afterEach(() => { vi.unstubAllGlobals(); void i18n.changeLanguage('en'); window.history.replaceState(null, '', '/') })

const now = Date.now() / 1000
const facts: WallFacts = {
  online: 93, seats: 112, online_max: 95, downloaded: 24.7e12, running_hours: 24,
  peak: { bps: 13.1e9, at: now - 60 }, busiest_hour: { bps: 3.4e9, t: now - 3600 },
  loyal_block: { name: 'A', share: 0.6, hours: 1.5 }, cache_saved: 846e9,
  games: [{ name: 'Steam', bar: 1 }, { name: 'Battle.net', bar: 0.3 }],
}

describe('PublicWall', () => {
  it('shows the hall in numbers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /wall.json': facts }).fn)
    const { container } = renderWithApp(<PublicWall />, '/wall')
    expect(await screen.findByText('Seats online now')).toBeInTheDocument()
    expect(container.querySelector('#wall-online')).toHaveTextContent('93of 112')
    expect(container.querySelector('#wall-downloaded')).toHaveTextContent('24.7TB')
    expect(container.querySelector('#wall-peak')).toHaveTextContent('13.1Gbit/s')
    expect(container.querySelector('#wall-loyal')).toHaveTextContent('Block A: each seat online 1.5 h on average')
    expect(screen.getByText('Steam')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/\b(AM|PM)\b/)
    expect(screen.getByText(/Buy me a coffee/)).toBeInTheDocument()
  })

  it('says when there is nothing yet', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /wall.json': { online: 0, seats: 0, games: [] } }).fn)
    renderWithApp(<PublicWall />, '/wall')
    expect(await screen.findByText(/Nothing to show yet/)).toBeInTheDocument()
  })

  it('fills the big screen without the attribution, in German', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    window.history.replaceState(null, '', '/wall?screen=1')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /wall.json': facts }).fn)
    const { container } = renderWithApp(<PublicWall />, '/wall?screen=1')
    expect(await screen.findByText('Plätze jetzt online')).toBeInTheDocument()
    expect(container.querySelector('.fb-wall--screen')).not.toBeNull()
    expect(screen.queryByText(/Buy me a coffee/)).toBeNull()
  })

  it('says when the page is switched off', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PublicWall />, '/wall')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page is switched off.')
  })

  it('writes numbers the way the language does', () => {
    expect(scaled(1.5e12, ['B', 'KB', 'MB', 'GB', 'TB'], 'de-CH')).toEqual(['1.5', 'TB'])
    expect(scaled(1.5e12, ['B', 'KB', 'MB', 'GB', 'TB'], 'de')).toEqual(['1,5', 'TB'])
    expect(scaled(846e9, ['B', 'KB', 'MB', 'GB', 'TB'], 'en')).toEqual(['846', 'GB'])
  })
})
