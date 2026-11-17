import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { EDIT_SHORTCUTS } from './edit/shortcuts'
import { TOOL_KEYS, TOOLS } from './edit/tools'
import { Shortcuts } from './Shortcuts'

describe('Keyboard shortcuts', () => {
  it('lists every editor tool with its own key', () => {
    const keys = TOOLS.map((id) => TOOL_KEYS[id])
    expect(new Set(keys).size).toBe(keys.length)
    const tools = EDIT_SHORTCUTS.find(([s]) => s === 'tools')![1]
    expect(tools.map(([[k]]) => k[0])).toEqual(keys.map((k) => k.toUpperCase()))
  })

  it('shows the editing keys while editing, the seat keys otherwise', () => {
    const { unmount } = renderWithApp(<Shortcuts opened onClose={() => {}} editing />)
    expect(screen.getByText('Editing keys')).toBeInTheDocument()
    expect(screen.getByText('Group the selection')).toBeInTheDocument()
    expect(screen.getByText('Distribution board')).toBeInTheDocument()
    unmount()
    const viewer = renderWithApp(<Shortcuts opened onClose={() => {}} />)
    expect(screen.getByText('Go from seat to seat')).toBeInTheDocument()
    expect(screen.queryByText(/Take up an editing tool/)).toBeNull()
    viewer.unmount()
    // Crew who may edit learn that a tool's key takes the editor up from the live plan.
    renderWithApp(<Shortcuts opened onClose={() => {}} canEdit />)
    expect(screen.getByText(/Take up an editing tool/)).toBeInTheDocument()
  })
})
