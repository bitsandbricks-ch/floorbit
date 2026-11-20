import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { Pane } from '../dashboards/model'
import { PaneForm } from '../dashboards/PaneForm'
import { PaneView } from '../dashboards/Panes'

const DOWN = { kind: 'tile', tile: 'floorbit/w/down', type: 'table' } as const
const widgets = { widgets: [{ id: 'down', name: 'Down switches', pane: DOWN, used_on: ['Wall'] }] }

afterEach(() => vi.unstubAllGlobals())

describe('saved widgets on a dashboard (#1009)', () => {
  it('clones the followed widget into a tile pane of its own', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/widgets': widgets }).fn)
    const onChange = vi.fn()
    const pane: Pane = { kind: 'widget', widget: 'down', saved: { name: 'Down switches', pane: DOWN } }
    renderWithApp(<PaneForm pane={pane} onChange={onChange} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Clone into this dashboard' }))
    expect(onChange).toHaveBeenCalledWith({ kind: 'tile', tile: 'floorbit/w/down', type: 'table', title: 'Down switches' })
  })

  it('says so when the saved widget is gone', () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PaneView pane={{ kind: 'widget', widget: 'gone', saved: null, title: 'Here' }} />)
    expect(screen.getByText(/This saved widget is gone/)).toBeInTheDocument()
  })
})
