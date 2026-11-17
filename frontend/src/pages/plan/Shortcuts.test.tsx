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

  it('shows the Edit mode keys while editing, the seat keys otherwise', () => {
    const { unmount } = renderWithApp(<Shortcuts opened onClose={() => {}} editing />)
    expect(screen.getByText('Edit mode keys')).toBeInTheDocument()
    expect(screen.getByText('Group the selection')).toBeInTheDocument()
    expect(screen.getByText('Distribution board')).toBeInTheDocument()
    unmount()
    renderWithApp(<Shortcuts opened onClose={() => {}} />)
    expect(screen.getByText('Go from seat to seat')).toBeInTheDocument()
  })
})
