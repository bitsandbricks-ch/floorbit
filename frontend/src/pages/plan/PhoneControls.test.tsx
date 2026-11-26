import { Menu } from '@mantine/core'
import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { PhoneControls } from './PhoneControls'

describe('PhoneControls', () => {
  it('floats the count, switches the view and opens sheets from the dock', async () => {
    const onView = vi.fn(), onLayers = vi.fn(), onProblems = vi.fn()
    renderWithApp(<PhoneControls search={<input aria-label="Find a seat" />} online={21} total={682} view="map" onView={onView}
      layersOn={4} onLayers={onLayers} problems={1} onProblems={onProblems}
      more={<Menu.Item>Show on a big screen</Menu.Item>} />)
    expect(screen.getByLabelText('21 / 682 online')).toHaveTextContent('21/682')
    fireEvent.click(screen.getByRole('button', { name: /Layers/ }))
    expect(onLayers).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Problems/ }))
    expect(onProblems).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'More' }))
    expect(await screen.findByText('Show on a big screen')).toBeInTheDocument()
    fireEvent.click(screen.getByText((_, el) => el?.getAttribute('aria-label') === 'List'))
    expect(onView).toHaveBeenCalledWith('list')
  })

  it('has no Layers in the list and no dock on the topology', () => {
    const props = { online: 1, total: 2, onView: () => {}, layersOn: 0, problems: 0, onProblems: () => {}, more: null }
    const { unmount } = renderWithApp(<PhoneControls {...props} view="list" />)
    expect(screen.queryByRole('button', { name: /Layers/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Problems/ })).toBeInTheDocument()
    unmount()
    renderWithApp(<PhoneControls {...props} view="topology" />)
    expect(screen.queryByRole('navigation')).toBeNull()
  })

  it('has an Edit button in the dock for those who may edit', () => {
    const onEdit = vi.fn()
    const props = { online: 1, total: 2, onView: () => {}, layersOn: 0, problems: 0, onProblems: () => {}, more: null }
    const { unmount } = renderWithApp(<PhoneControls {...props} view="map" onEdit={onEdit} />)
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(onEdit).toHaveBeenCalled()
    unmount()
    renderWithApp(<PhoneControls {...props} view="map" />)
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })
})
