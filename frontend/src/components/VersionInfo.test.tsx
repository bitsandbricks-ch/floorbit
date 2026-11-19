import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { VersionInfo } from './VersionInfo'

afterEach(() => vi.unstubAllGlobals())

const SHA = '0123456789abcdef0123456789abcdef01234567'

describe('version line', () => {
  it('names the release, links the commit and shows the build date and agent', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/version': { api: 1, app: '1.2.0', release: '1.2.0', commit: SHA, built: 1795073400,
        source: 'https://github.com/example/floorbit', dev: false, agents: [{ name: 'Hall', version: '0.4.1' }] },
    }).fn)
    renderWithApp(<VersionInfo />)
    const release = await screen.findByRole('link', { name: 'Floorbit 1.2.0' })
    expect(release).toHaveAttribute('href', 'https://github.com/example/floorbit/releases/tag/v1.2.0')
    expect(screen.getByRole('link', { name: '0123456' })).toHaveAttribute('href', `https://github.com/example/floorbit/commit/${SHA}`)
    expect(screen.getByText(/^built /)).toHaveTextContent('2026')
    expect(screen.getByText('Agent 0.4.1')).toBeInTheDocument()
  })

  it('marks a build without a release as dev and leaves out what it does not know', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/version': { api: 1, app: '0.1.0', release: null, commit: null, built: null, dev: true } }).fn)
    renderWithApp(<VersionInfo />)
    expect(await screen.findByText('Floorbit 0.1.0')).toBeInTheDocument()
    expect(screen.getByText('dev build')).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.queryByText(/^built /)).toBeNull()
  })
})
