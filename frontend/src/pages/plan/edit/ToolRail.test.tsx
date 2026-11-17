import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { EDIT_SHORTCUTS } from './shortcuts'
import { ToolRail } from './ToolRail'
import { TOOL_KEYS, TOOLS } from './tools'

describe('Tool rail', () => {
  it('has one button per tool with its key, and only the current one pressed', () => {
    const onTool = vi.fn()
    const onView = vi.fn()
    renderWithApp(<ToolRail tool="wall" onTool={onTool} onView={onView} />)
    const bar = screen.getByRole('toolbar', { name: 'Tools' })
    const buttons = bar.querySelectorAll('button[aria-keyshortcuts]')
    expect(buttons).toHaveLength(TOOLS.length)
    expect([...buttons].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.getAttribute('aria-keyshortcuts'))).toEqual(['W'])
    fireEvent.click(buttons[TOOLS.indexOf('zone')])
    expect(onTool).toHaveBeenCalledWith('zone')
    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    expect(onView).toHaveBeenCalled()
  })

  it('shows View pressed while no tool is in hand', () => {
    renderWithApp(<ToolRail tool={null} onTool={vi.fn()} onView={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'View' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^Select/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('gives every single-key shortcut in Edit mode one meaning only', () => {
    const single = EDIT_SHORTCUTS.flatMap(([, rows]) => rows.flatMap(([alts]) => alts.filter((keys) => keys.length === 1 && /^[A-Z]$/.test(keys[0])).map((k) => k[0])))
    expect(single.length).toBeGreaterThan(TOOLS.length)
    expect(new Set(single).size).toBe(single.length)
    expect(new Set(Object.values(TOOL_KEYS)).size).toBe(TOOLS.length)
  })
})
