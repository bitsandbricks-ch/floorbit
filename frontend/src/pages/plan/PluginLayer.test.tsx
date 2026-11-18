import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlanSeat } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PluginLayerPicker } from './PluginLayer'
import { SeatGlyph } from './SeatMap'
import { usePluginLayer } from './pluginLayerQuery'

afterEach(() => vi.unstubAllGlobals())

function Probe({ chosen, name }: { chosen: string | null; name: string }) {
  const { layers, data } = usePluginLayer(chosen)
  if (!layers.length || (chosen && !data)) return null
  return <span data-testid={name}>{layers.length} {data?.seats['A-1'].tone ?? '-'}</span>
}

const layer = { plugin: 'hallthing', plugin_name: 'Hall thing', icon: 'chart', id: 'load', label: 'Seat load', refresh: 30,
  url: '/api/plugins/hallthing/layers/load' }

describe('plugin layers', () => {
  it('lists the layers and loads only the chosen one', async () => {
    const api = fakeFetch({
      'GET /api/plugins/layers': { layers: [layer] },
      'GET /api/plugins/hallthing/layers/load': { seats: { 'A-1': { tone: 'err', label: 'Down' } }, legend: [{ tone: 'err', label: 'Down' }] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<><Probe chosen={null} name="none" /><Probe chosen="hallthing/load" name="chosen" /></>)
    expect(await screen.findByTestId('chosen')).toHaveTextContent('1 err')
    expect(screen.getByTestId('none')).toHaveTextContent('1 -')
    expect(api.calls.filter((c) => c.path.includes('/layers/load'))).toHaveLength(1)
  })

  it('shows the picker and the legend, and nothing without plugin layers', () => {
    const { container, unmount } = renderWithApp(<PluginLayerPicker layers={[]} value={null} onChange={() => {}} />)
    expect(container.querySelector('.fb-plugin-layer')).toBeNull()
    unmount()
    renderWithApp(<PluginLayerPicker layers={[layer]} value="hallthing/load" onChange={() => {}}
      data={{ seats: {}, legend: [{ tone: 'ok', label: 'Up' }, { tone: 'err', label: 'Down' }] }} />)
    expect(screen.getByRole('combobox', { name: 'Plugin layer' })).toHaveValue('Hall thing: Seat load')
    expect(screen.getByLabelText('What the plugin layer shows')).toHaveTextContent('UpDown')
  })

  it('rings a seat in the tone the layer gives it', () => {
    const seat = { state: 'online' } as PlanSeat
    const { container } = renderWithApp(<svg><SeatGlyph seat={seat} size={20} detail mark="warn" /></svg>)
    expect(container.querySelector('rect.pl.pl-warn')).not.toBeNull()
  })
})
