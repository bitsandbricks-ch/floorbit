import { act, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import PublicAgenda, { type Agenda } from './PublicAgenda'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); void i18n.changeLanguage('en'); window.history.replaceState(null, '', '/') })

const now = Math.floor(Date.now() / 1000)
const item = (over: Partial<Agenda['items'][0]>) => ({ id: over.title ?? 'x', title: 'x', kind: 'other' as const, start: now, end: null, where: '', note: '', ...over })
const agenda = (over: Partial<Agenda> = {}): Agenda => ({
  event: { start: null, end: null }, phase: 'during', countdown: null, now: [], next: [], quiet: null, items: [],
  server_time: now, ...over,
})

describe('PublicAgenda', () => {
  it('counts down to the start on the server clock', async () => {
    const start = now + 2 * 86400 + 3 * 3600 + 5
    const opening = item({ title: 'Opening', kind: 'talk', start, where: 'Main stage' })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /agenda.json': agenda({ phase: 'before', event: { start, end: null },
      countdown: start - now, next: [opening], items: [opening] }) }).fn)
    const { container } = renderWithApp(<PublicAgenda />, '/agenda')
    expect(await screen.findByText('The event starts in')).toBeInTheDocument()
    expect(container.querySelector('#countdown b')).toHaveTextContent('2')
    expect(container.querySelector('#agenda-next')).toHaveTextContent('Opening')
    expect(screen.getByRole('link', { name: /Add the programme/ })).toHaveAttribute('href', '/agenda.ics')
  })

  it('shows now, quiet hours and the programme by day, in 24 hours', async () => {
    const dinner = item({ title: 'Dinner', kind: 'meal', start: now - 600, end: now + 600, where: 'Bar' })
    const quiet = item({ title: 'Quiet', kind: 'quiet', start: now - 60, end: now + 3600 })
    const past = item({ title: 'Doors open', start: now - 7200 })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /agenda.json': agenda({ now: [dinner, quiet], quiet, items: [past, dinner, quiet] }) }).fn)
    const { container } = renderWithApp(<PublicAgenda />, '/agenda')
    expect(await screen.findByText(/Quiet hours until/)).toBeInTheDocument()
    expect(container.querySelector('#agenda-now')).toHaveTextContent('Dinner')
    expect(container.querySelector('#agenda-now')).not.toHaveTextContent('Quiet')
    expect(container.querySelectorAll('.fb-agenda-day').length).toBeGreaterThanOrEqual(1)
    expect(container.querySelector('.fb-agenda-past')).toHaveTextContent('Doors open')
    expect(container.textContent).not.toMatch(/\b(AM|PM)\b/)
  })

  it('says when the event is over', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /agenda.json': agenda({ phase: 'after' }) }).fn)
    renderWithApp(<PublicAgenda />, '/agenda')
    expect(await screen.findByText(/The event is over/)).toBeInTheDocument()
    expect(screen.getByText('The programme is not out yet.')).toBeInTheDocument()
  })

  it('fills the big screen in German, without the calendar link', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    window.history.replaceState(null, '', '/agenda?screen=1')
    const start = now + 3600
    vi.stubGlobal('fetch', fakeFetch({ 'GET /agenda.json': agenda({ phase: 'before', event: { start, end: null }, countdown: 3600,
      items: [item({ title: 'Opening', start })] }) }).fn)
    const { container } = renderWithApp(<PublicAgenda />, '/agenda?screen=1')
    expect(await screen.findByText('Der Event beginnt in')).toBeInTheDocument()
    expect(container.querySelector('.fb-agenda--screen')).not.toBeNull()
    expect(screen.queryByRole('link', { name: /Kalender/ })).toBeNull()
  })

  it('leaves past items off the big screen', async () => {
    window.history.replaceState(null, '', '/agenda?screen=1')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /agenda.json': agenda({ phase: 'after',
      items: [item({ title: 'Doors open', start: now - 7200 })] }) }).fn)
    const { container } = renderWithApp(<PublicAgenda />, '/agenda?screen=1')
    expect(await screen.findByText(/The event is over/)).toBeInTheDocument()
    expect(container.querySelector('.fb-agenda-programme')).toBeNull()
    expect(screen.queryByText('Doors open')).toBeNull()
  })

  it('says when the page is switched off', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PublicAgenda />, '/agenda')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page is switched off.')
  })
})
