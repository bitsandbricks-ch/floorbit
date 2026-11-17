import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Circuit } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BoardFields, PlaceBoardDialog } from './PowerFields'

afterEach(() => vi.unstubAllGlobals())

describe('New distribution board dialog', () => {
  it('suggests the next free name and places it with its location, both trimmed', async () => {
    const onCreate = vi.fn<(body: { name: string; location: string }) => Promise<boolean>>(() => Promise.resolve(true))
    renderWithApp(<PlaceBoardDialog opened names={['DB-1']} onClose={() => {}} onCreate={onCreate} />)
    expect(await screen.findByLabelText(/^Name/)).toHaveValue('DB-2')
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: ' stage left ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Place board' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith({ name: 'DB-2', location: 'stage left' }))
  })

  it('can not be placed without a name', async () => {
    renderWithApp(<PlaceBoardDialog opened names={[]} onClose={() => {}} onCreate={() => Promise.resolve(true)} />)
    const name = await screen.findByLabelText(/^Name/)
    expect(name).toHaveValue('DB-1')
    fireEvent.change(name, { target: { value: '  ' } })
    expect(screen.getByRole('button', { name: 'Place board' })).toBeDisabled()
  })
})

const circuit = (id: string, board: string, extra: Partial<Circuit> = {}) =>
  ({ id, board, name: id, state: 'ok', load_pct: 42, feeds_label: '', ...extra }) as unknown as Circuit

describe('Distribution board fields', () => {
  function fields(feedable: number) {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/power': { circuits: [
      circuit('C1', 'DB-1', { feeds_label: 'Block A' } as Partial<Circuit>),
      circuit('C2', 'DB-1', { state: 'tripped', load_pct: null }),
      circuit('C9', 'DB-2'),
    ] } }).fn)
    const onAddCircuit = vi.fn<(name: string) => Promise<void>>(() => Promise.resolve())
    const onFeed = vi.fn<(c: Circuit) => Promise<void>>(() => Promise.resolve())
    renderWithApp(<BoardFields board="DB-1" feedable={feedable} onAddCircuit={onAddCircuit} onFeed={onFeed} />)
    return { onAddCircuit, onFeed }
  }

  it('lists only this board\'s circuits with what they feed and their load', async () => {
    fields(0)
    expect(await screen.findByText('2 circuits')).toBeInTheDocument()
    expect(screen.getByText('Block A')).toBeInTheDocument()
    expect(screen.getByText('feeds nothing yet')).toBeInTheDocument()
    expect(screen.getByText('42 %')).toBeInTheDocument()
    expect(screen.getByText('Tripped')).toBeInTheDocument()
    expect(screen.queryByText('C9')).toBeNull()
    expect(screen.getByText('Shift-click seat blocks or switches to feed them from this board.')).toBeInTheDocument()
  })

  it('adds a circuit by its trimmed name and clears the field', async () => {
    const { onAddCircuit } = fields(0)
    const input = await screen.findByLabelText('New circuit')
    fireEvent.change(input, { target: { value: ' C3 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(onAddCircuit).toHaveBeenCalledWith('C3'))
    await waitFor(() => expect(input).toHaveValue(''))
  })

  it('feeds the selected items from the chosen circuit', async () => {
    const { onFeed } = fields(2)
    const feed = await screen.findByRole('button', { name: 'Feed' })
    expect(feed).toBeDisabled()
    fireEvent.click(screen.getByRole('combobox', { name: 'Feed the 2 selected items from' }))
    fireEvent.click(await screen.findByRole('option', { name: 'C1', hidden: true }))
    fireEvent.click(feed)
    await waitFor(() => expect(onFeed).toHaveBeenCalledTimes(1))
    expect(onFeed.mock.calls[0][0]).toMatchObject({ id: 'C1', board: 'DB-1' })
  })
})
