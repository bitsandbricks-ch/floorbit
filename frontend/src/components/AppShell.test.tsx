import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { AppShell } from './Layout'

afterEach(() => vi.unstubAllGlobals())

describe('the crew frame', () => {
  it('frames crew pages', () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    const { container } = renderWithApp(<AppShell><p>plan</p></AppShell>, '/plan')
    expect(container.querySelector('.bnb-shell')).not.toBeNull()
  })
  it.each(['/plan?screen=1&hall=main', '/plan?print=1'])('leaves %s alone, for the wall screen or the paper', (route) => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    const { container } = renderWithApp(<AppShell><p>plan</p></AppShell>, route)
    expect(screen.getByText('plan')).toBeInTheDocument()
    expect(container.querySelector('.bnb-shell')).toBeNull()
  })
})
