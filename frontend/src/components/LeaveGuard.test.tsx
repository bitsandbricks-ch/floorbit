import { fireEvent, screen } from '@testing-library/react'
import { useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { inSettings } from '@/pages/settings/model'
import { LeaveGuard } from './LeaveGuard'
import { useLeaveWarning } from './useLeaveWarning'

function Form() {
  const [dirty, setDirty] = useState(false)
  useLeaveWarning(dirty, (p) => p.startsWith('/form'))
  return (
    <>
      <button type="button" onClick={() => setDirty(true)}>Type</button>
      <Link to="/form/other">Another tab</Link>
      <Link to="/elsewhere">Elsewhere</Link>
    </>
  )
}

const app = () => renderWithApp(
  <><LeaveGuard /><Routes>
    <Route path="/form/*" element={<Form />} />
    <Route path="/elsewhere" element={<p>Arrived</p>} />
  </Routes></>, '/form')

describe('LeaveGuard (#993)', () => {
  it('lets links go while nothing is unsaved', async () => {
    app()
    fireEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    expect(await screen.findByText('Arrived')).toBeInTheDocument()
  })

  it('asks before a link leaves unsaved changes, and goes only when told to', async () => {
    app()
    fireEvent.click(screen.getByRole('button', { name: 'Type' }))
    fireEvent.click(screen.getByRole('link', { name: 'Another tab' }))   // kept: no question
    expect(screen.queryByText('Leave without saving?')).toBeNull()
    fireEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    expect(await screen.findByText('Leave without saving?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stay' }))
    expect(screen.queryByText('Arrived')).toBeNull()
    fireEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Leave without saving' }))
    expect(await screen.findByText('Arrived')).toBeInTheDocument()
  })

  it('keeps Settings changes across its entries, not into another page', () => {
    expect(inSettings('/settings')).toBe(true)
    expect(inSettings('/settings/discord')).toBe(true)
    expect(inSettings('/settings/plugins')).toBe(false)
    expect(inSettings('/settings/agents/a1')).toBe(false)
    expect(inSettings('/plan')).toBe(false)
  })
})
