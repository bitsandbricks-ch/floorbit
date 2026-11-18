import { act, fireEvent, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import PublicBracket, { type PublicBracketData } from './PublicBracket'

afterEach(() => { vi.unstubAllGlobals(); void i18n.changeLanguage('en'); window.history.replaceState(null, '', '/') })

const side = (name: string | null, score: number | null = null) => ({ name, score })
const cup: PublicBracketData = {
  id: 'cup', name: 'Rocket Cup', zone: 'Main stage', champion: null, live: 1, rounds: [
    { n: 1, label: 'semi', matches: [
      { id: 'r1m1', a: side('Aurora', 2), b: side('Respawn', 0), status: 'done', winner: 'a' },
      { id: 'r1m2', a: side('Byte'), b: side('Lag'), status: 'live', winner: null, station: 'Stage PC 1' }] },
    { n: 2, label: 'final', matches: [{ id: 'r2m1', a: side('Aurora'), b: side(null), status: 'open', winner: null }] },
  ],
}
const other: PublicBracketData = { id: 'cs', name: 'CS Cup', zone: null, champion: 'Zeta', rounds: [] }

describe('PublicBracket', () => {
  it('draws the rounds, the live match and who won', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /bracket.json': { brackets: [cup, other] } }).fn)
    const { container } = renderWithApp(<PublicBracket />, '/bracket')
    expect(await screen.findByRole('heading', { name: 'Rocket Cup' })).toBeInTheDocument()
    expect(screen.getByText('Semi-finals')).toBeInTheDocument()
    expect(screen.getByText('Final')).toBeInTheDocument()
    expect(container.querySelector('[data-match="r1m2"]')).toHaveTextContent('Live')
    expect(container.querySelector('[data-match="r1m2"]')).toHaveTextContent('Stage PC 1')
    expect(container.querySelector('.fb-pbr-team.won')).toHaveTextContent('Aurora2')
    expect(screen.getByText('to be decided')).toBeInTheDocument()
    // More than one bracket: pick another.
    fireEvent.click(screen.getByRole('radio', { name: 'CS Cup' }))
    expect(await screen.findByText('Zeta')).toBeInTheDocument()
    expect(screen.getByText('Champion')).toBeInTheDocument()
  })

  it('opens the bracket ?id= names, without picker on the big screen, in German', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    window.history.replaceState(null, '', '/bracket?screen=1&id=cup')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /bracket.json': { brackets: [other, cup] } }).fn)
    const { container } = renderWithApp(<PublicBracket />, '/bracket?screen=1&id=cup')
    expect(await screen.findByText('Halbfinals')).toBeInTheDocument()
    expect(container.querySelector('.fb-pbr-page--screen')).not.toBeNull()
    expect(screen.queryByRole('radio')).toBeNull()
  })

  it('says when there are none, or the page is off', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /bracket.json': { brackets: [] } }).fn)
    renderWithApp(<PublicBracket />, '/bracket')
    expect(await screen.findByText('No brackets yet.')).toBeInTheDocument()
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PublicBracket />, '/bracket')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page is switched off.')
  })
})
