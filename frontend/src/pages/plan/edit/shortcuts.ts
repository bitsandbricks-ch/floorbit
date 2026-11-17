import { TOOL_KEYS, TOOLS } from './tools'

/** Edit mode's keys, by section: each row is the keys (alternatives) and the text key that says
 *  what they do. Tools come from TOOL_KEYS, so the list can't drift from what the editor does. */
export type KeyRow = [string[][], string]
export const EDIT_SHORTCUTS: [string, KeyRow[]][] = [
  ['tools', TOOLS.map((id) => [[[TOOL_KEYS[id].toUpperCase()]], `tool.${id}`] as KeyRow)],
  ['select', [
    [[['Shift', 'Click']], 'addSelect'],
    [[['Tab'], ['Shift', 'Tab']], 'cycle'],
    [[['Ctrl', 'A']], 'all'],
    [[['Ctrl', 'Shift', 'A']], 'similar'],
    [[['Esc']], 'deselect'],
  ]],
  ['move', [
    [[['←', '↑', '→', '↓']], 'nudge'],
    [[['Shift', '←↑→↓']], 'nudgeMore'],
    [[['Alt', 'Drag']], 'free'],
    [[['Space', 'Drag']], 'pan'],
    [[['F']], 'frame'],
  ]],
  ['change', [
    [[['Ctrl', 'Z']], 'undo'],
    [[['Ctrl', 'Shift', 'Z'], ['Ctrl', 'Y']], 'redo'],
    [[['Ctrl', 'C'], ['Ctrl', 'X'], ['Ctrl', 'V']], 'clipboard'],
    [[['Ctrl', 'D']], 'duplicate'],
    [[['Ctrl', 'G']], 'group'],
    [[['Ctrl', 'Shift', 'G']], 'ungroup'],
    [[['Ctrl', ']'], ['Ctrl', '[']], 'stack'],
    [[['R'], ['Shift', 'R']], 'rotate'],
    [[['Del'], ['Backspace']], 'delete'],
  ]],
  ['help', [[[['?']], 'help']]],
]
