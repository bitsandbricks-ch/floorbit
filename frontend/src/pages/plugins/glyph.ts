import { IconPuzzle, type Icon } from '@tabler/icons-react'
import { CUSTOM_ICONS } from '@/nav/sections'
import { DEVICE_ICONS } from '@/pages/inventory/icons'

/** A plugin's `icon:` (floorbit/plugins plugin_icons: the sidebar's and the inventory's sets); a
 *  name this page doesn't know shows the puzzle piece, never anything the plugin sent. */
export function pluginGlyph(name?: string): Icon {
  if (!name) return IconPuzzle
  // Own keys only: a name like "constructor" must not reach Object's prototype.
  if (Object.hasOwn(CUSTOM_ICONS, name)) return CUSTOM_ICONS[name]
  if (Object.hasOwn(DEVICE_ICONS, name)) return DEVICE_ICONS[name]
  return IconPuzzle
}
