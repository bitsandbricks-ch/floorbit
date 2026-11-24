import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BoardPage } from './BoardPage'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

const board = (fit: boolean) => ({
  id: 'ops', name: 'Ops', fit, sections: [{ panels: [{ x: 0, y: 0, w: 8, h: 4, node: { pane: { kind: 'text', text: 'Hello', size: 'm', align: 'start' } } }] }],
})

const show = (fit: boolean) => {
  vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards/ops': board(fit), 'GET /api/me': { user: 'demo', permissions: [] } }).fn)
  return renderWithApp(<Routes><Route path="/dashboards/view/:id" element={<BoardPage id="ops" />} /></Routes>, '/dashboards/view/ops')
}

describe('A dashboard in the app', () => {
  it('fits a Screen dashboard under the top bar', async () => {
    const { container } = show(true)
    expect(await screen.findByText('Hello')).toBeInTheDocument()
    expect(container.querySelector('.fb-board-inline.fit .fb-grid.fit')).not.toBeNull()
  })

  it('lets a Page dashboard scroll', async () => {
    const { container } = show(false)
    expect(await screen.findByText('Hello')).toBeInTheDocument()
    expect(container.querySelector('.fb-grid.fit')).toBeNull()
  })
})
