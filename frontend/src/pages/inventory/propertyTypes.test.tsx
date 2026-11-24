import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PropertyDef } from '@/api/properties'
import { fakeFetch, renderWithApp } from '@/test/render'
import PropertiesPage from './PropertiesPage'
import { PropertiesEditor } from './ScopeEditors'

afterEach(() => vi.unstubAllGlobals())

const def = (p: Partial<PropertyDef> & Pick<PropertyDef, 'key' | 'type'>): PropertyDef =>
  ({ label: p.key, unit: '', choices: [], roles: [], hint: '', builtin: false, ...p })
const properties = [
  def({ key: 'telemetry.verify_tls', type: 'bool', label: 'Check the TLS certificate', builtin: true }),
  def({ key: 'poe.budget', type: 'number', label: 'PoE budget', unit: 'W', roles: ['switch'] }),
  def({ key: 'side', type: 'choice', choices: ['left', 'right'], roles: ['server'] }),
]
const admin = { enabled: true, user: { username: 'ad', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }

describe('known properties (#879)', () => {
  it('gives a known property its input and marks an unknown one', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/inventory/properties': { properties, types: [] } }).fn)
    const onSave = vi.fn()
    renderWithApp(<PropertiesEditor value={{ 'poe.budget': '370', rack: 'A1' }} role="switch" canEdit busy={false} onSave={onSave} />)
    expect(await screen.findByText('PoE budget')).toBeInTheDocument()
    expect(screen.getByText('W')).toBeInTheDocument()
    expect(screen.getByText('custom, untyped')).toBeInTheDocument()
  })

  it('lists them and lets an admin add one', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/inventory/properties': { properties, types: [] },
      'POST /api/inventory/properties': () => ({ status: 201, body: def({ key: 'rack.u', type: 'number' }) }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PropertiesPage />, '/inventory/properties')
    expect(await screen.findByText('telemetry.verify_tls')).toBeInTheDocument()
    expect(screen.getByText('Built in')).toBeInTheDocument()
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'rack.u' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add property' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && (c.body as { key: string }).key === 'rack.u')).toBe(true))
  })
})
