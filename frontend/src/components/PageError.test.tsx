import { fireEvent, screen } from '@testing-library/react'
import { Link, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { isStaleCode } from '@bitsandbricks/ui'
import { renderWithApp } from '@/test/render'
import { AppShell } from './Layout'

function Broken(): never {
  throw new Error('cannot read properties of undefined')
}

function shell() {
  return renderWithApp(
    <>
      <Link to="/fine">to the fine page</Link>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/broken" element={<Broken />} />
          <Route path="/fine" element={<p>Fine page</p>} />
        </Route>
      </Routes>
    </>,
    '/broken',
  )
}

describe('PageError', () => {
  afterEach(() => vi.restoreAllMocks())

  it('keeps the sidebar and offers a reload when a page throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    shell()
    expect(screen.getByRole('alert')).toHaveTextContent('This page hit an error')
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
    expect(screen.getByText('cannot read properties of undefined')).toBeInTheDocument()
    expect(screen.getAllByRole('navigation').length).toBeGreaterThan(0)   // the sidebar is still there
  })

  it('starts over on another page', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    shell()
    expect(screen.getByRole('alert')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'to the fine page' }))
    expect(await screen.findByText('Fine page')).toBeInTheDocument()
    expect(screen.queryByText('This page hit an error')).not.toBeInTheDocument()
  })

  it('tells an update from a bug', () => {
    expect(isStaleCode(new TypeError('Failed to fetch dynamically imported module: /assets/Gear-abc.js'))).toBe(true)
    expect(isStaleCode(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isStaleCode(new Error('cannot read properties of undefined'))).toBe(false)
  })
})
