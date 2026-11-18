import { ThemeIcon } from '@mantine/core'
import { createElement } from 'react'
import { pluginGlyph } from './glyph'

export function PluginIcon({ name, size = 28 }: { name?: string; size?: number }) {
  return (
    <ThemeIcon variant="light" color="bit" size={size} radius="md" aria-hidden>
      {createElement(pluginGlyph(name), { size: Math.round(size * 0.62), stroke: 1.6 })}
    </ThemeIcon>
  )
}
