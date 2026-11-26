import { IconFileDiff, IconTerminal, IconTerminal2 } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Switch console: commands, the terminal and configs as tabs.
export const area: NavArea = {
  hub: 'console',
  tabs: ['commands', 'terminal', 'configs'],
  icons: {
    console: IconTerminal2,
    commands: IconTerminal2,
    terminal: IconTerminal,
    configs: IconFileDiff,
  },
}
