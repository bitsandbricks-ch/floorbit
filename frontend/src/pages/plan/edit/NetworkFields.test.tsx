import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlanCable } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { CableFields, PanelFields, PlacePanelDialog } from './NetworkFields'

afterEach(() => vi.unstubAllGlobals())

describe('New patch panel dialog', () => {
  it('suggests the next free name, refuses one in use, and places it with the chosen ports', async () => {
    const onCreate = vi.fn<(body: { name: string; ports: number }) => Promise<boolean>>(() => Promise.resolve(true))
    renderWithApp(<PlacePanelDialog opened names={['PP-01', 'PP-02']} onClose={() => {}} onCreate={onCreate} />)
    const name = await screen.findByLabelText(/^Name/)
    expect(name).toHaveValue('PP-03')
    fireEvent.change(name, { target: { value: 'pp-01' } })
    expect(screen.getByText('There is a patch panel with that name already.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Place' })).toBeDisabled()
    fireEvent.change(name, { target: { value: ' Stage ' } })
    fireEvent.click(screen.getByText('48'))
    fireEvent.click(screen.getByRole('button', { name: 'Place' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith({ name: 'Stage', ports: 48 }))
  })

  it('starts at PP-01 when there are none', async () => {
    renderWithApp(<PlacePanelDialog opened names={[]} onClose={() => {}} onCreate={() => Promise.resolve(true)} />)
    expect(await screen.findByLabelText(/^Name/)).toHaveValue('PP-01')
  })
})

describe('Patch panel fields', () => {
  const panel = { name: 'PP-01', x: 10, y: 10, ports: 2, used: 2 }

  it('shows how full it is and who is on each port', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/options/panel-ports?panel=PP-01': { options: [{ value: '1', label: '1', used: 'D-1' }, { value: '2', label: '2', used: '' }] } }).fn)
    renderWithApp(<PanelFields panel={panel} onPorts={() => Promise.resolve()} />)
    expect(screen.getByText('2 of 2 ports in use')).toBeInTheDocument()
    expect(screen.getByText('Full')).toBeInTheDocument()
    const ports = await screen.findByRole('list', { name: 'Ports' })
    expect(ports.textContent).toBe('1 D-12')
  })

  it('saves a new port count with the old one, once', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/options/panel-ports?panel=PP-01': { options: [] } }).fn)
    const onPorts = vi.fn<(before: number, after: number) => Promise<void>>(() => Promise.resolve())
    renderWithApp(<PanelFields panel={panel} onPorts={onPorts} />)
    const input = screen.getByLabelText('Ports')
    fireEvent.blur(input)
    fireEvent.change(input, { target: { value: '24' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(onPorts).toHaveBeenCalledWith(2, 24))
    expect(onPorts).toHaveBeenCalledTimes(1)
  })
})

describe('Cable fields', () => {
  const cable = {
    key: 'c1', kind: 'lan', layer: 'network', points: [], manual: true, corners: 'square', via: 'PP-01', label: '',
    ref: { switch: 'sw-a-01', port: 'Gi1/0/3', seat: 'A-3', source: 'import' },
  } as PlanCable

  it('says where the cable runs, and offers the corners, the automatic route and the form', () => {
    const onCorners = vi.fn(), onReset = vi.fn(), onEdit = vi.fn()
    renderWithApp(<CableFields cable={cable} onEdit={onEdit} onCorners={onCorners} onReset={onReset} />)
    expect(screen.getByText('sw-a-01 Gi1/0/3')).toBeInTheDocument()
    expect(screen.getByText('PP-01')).toBeInTheDocument()
    expect(screen.getByText('Imported: change it in the source and import again.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Round'))
    expect(onCorners).toHaveBeenCalledWith('round')
    fireEvent.click(screen.getByRole('button', { name: 'Back to the automatic route' }))
    expect(onReset).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Change cable' }))
    expect(onEdit).toHaveBeenCalled()
  })

  it('has no way back to the automatic route for a cable that already takes it', () => {
    renderWithApp(<CableFields cable={{ ...cable, manual: false, via: null }} onEdit={() => {}} onCorners={() => {}} onReset={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Back to the automatic route' })).toBeNull()
    expect(screen.queryByText('Patch panel')).toBeNull()
  })
})
