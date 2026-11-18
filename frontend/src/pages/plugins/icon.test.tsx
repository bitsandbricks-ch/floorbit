import { IconPuzzle, IconShield } from '@tabler/icons-react'
import { describe, expect, it } from 'vitest'
import { renderWithApp } from '@/test/render'
import { pluginGlyph } from './glyph'
import { PluginIcon } from './icon'

describe('PluginIcon', () => {
  it('draws a known name and falls back for anything else', () => {
    expect(pluginGlyph('shield')).toBe(IconShield)
    for (const name of ['', undefined, 'constructor', '__proto__', 'toString', 'nope']) expect(pluginGlyph(name)).toBe(IconPuzzle)
    const { container } = renderWithApp(<PluginIcon name="router" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
