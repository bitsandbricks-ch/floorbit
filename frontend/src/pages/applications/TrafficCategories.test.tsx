import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BUILTIN_CATEGORIES } from '@/api/trafficCategories'
import { fakeFetch, renderWithApp } from '@/test/render'
import { TrafficCategories } from './TrafficCategories'

afterEach(() => vi.unstubAllGlobals())

const answer = { categories: BUILTIN_CATEGORIES, palette: ['#dc2626', '#ea580c'], max_own: 30 }

describe('TrafficCategories', () => {
  it('adds an own category with a name, a German name and a colour', async () => {
    const saved = { ...answer, categories: [...BUILTIN_CATEGORIES,
      { id: 'example-cup', name: 'Example Cup', name_de: 'Beispiel-Cup', colour: '#ea580c', builtin: false }] }
    const fake = fakeFetch({ 'GET /api/traffic/categories': answer, 'PUT /api/traffic/categories': saved })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<TrafficCategories onClose={() => {}} />)
    expect(await screen.findByText('Streaming')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Add a category' }))
    fireEvent.change(screen.getByRole('textbox', { name: /^Name\s*\*?$/ }), { target: { value: 'Example Cup' } })
    fireEvent.change(screen.getByLabelText('Name in German'), { target: { value: 'Beispiel-Cup' } })
    fireEvent.click(screen.getByRole('radio', { name: '#ea580c' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Categories saved')).toBeInTheDocument()
    const put = fake.calls.find((c) => c.method === 'PUT')
    expect(put?.body).toEqual({ categories: [{ id: 'example-cup', name: 'Example Cup', name_de: 'Beispiel-Cup', colour: '#ea580c' }] })
  })
})
