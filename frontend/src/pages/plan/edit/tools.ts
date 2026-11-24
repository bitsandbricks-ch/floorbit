import { type BlockRow, rowCount } from './rows'
/** The Edit mode's tools. Each keeps going after placing something (sticky, like the older editor);
 *  Esc or V goes back to Select. Hand only moves the view, like Space + drag;
 *  Measure draws a line that only shows its length and angle. */
export const TOOLS = ['select', 'hand', 'measure', 'block', 'switch', 'text', 'icon', 'wall', 'zone', 'panel', 'cable', 'board'] as const
export type Tool = (typeof TOOLS)[number]

export const TOOL_KEYS: Record<Tool, string> = { select: 'v', hand: 'h', measure: 'm', block: 'b', switch: 's', text: 't', icon: 'i', wall: 'w', zone: 'z', panel: 'p', cable: 'c', board: 'e' }

/** How a tool takes the pointer: a click places, a drag draws a line or a box, or pans the view. */
export const TOOL_GESTURE: Record<Tool, 'select' | 'pan' | 'click' | 'line' | 'box' | 'measure'> = {
  select: 'select', hand: 'pan', measure: 'measure', block: 'click', switch: 'click', text: 'click', icon: 'click', wall: 'line', zone: 'box', panel: 'click', cable: 'click', board: 'click',
}

/** Row letters like the server's (floorbit/seat_names.py): 0 -> A, 25 -> Z, 26 -> AA. */
export function rowLetter(index: number): string {
  let out = ''
  let n = index + 1
  while (n > 0) {
    const rest = (n - 1) % 26
    out = String.fromCharCode(65 + rest) + out
    n = Math.floor((n - 1) / 26)
  }
  return out
}

export function letterIndex(letters: string): number {
  let n = 0
  for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64)
  return n - 1
}

/** The first row letter after every letter in use (all halls), for a new block: the rows of blocks
 *  named by row, and the names of blocks named by block (their seats are A-1, A-2 …). */
export function nextFreeRow(blocks: { naming?: string; row_start?: string; rows?: number | BlockRow[]; name?: string }[]): string {
  const letters = /^[A-Z]{1,2}$/i
  let next = 0
  for (const b of blocks) {
    if (b.naming === 'rows' && b.row_start && letters.test(b.row_start)) next = Math.max(next, letterIndex(b.row_start) + rowCount(b.rows))
    else if (b.naming !== 'rows' && b.name && letters.test(b.name)) next = Math.max(next, letterIndex(b.name) + 1)
  }
  return rowLetter(next)
}

/** How far apart (in % of the plan) copies of a new block go: its size plus the gap. Seats are 2 %
 *  wide and 3.2 % tall (32 drawing units on 1600 x 1000), with room for row letters and a name. */
export function blockStep(v: { cols: number; rows: number; naming: string; row_labels: string; name: string; rotation: number },
  gap: number, direction: 'down' | 'right') {
  const labelled = v.naming === 'rows' && v.row_labels !== 'none'
  const extra = labelled ? (v.row_labels === 'both' ? 2 : 1) : 0
  let w = (v.cols + extra) * 2 + 1
  let h = v.rows * 3.2 + 1.6 + (v.name ? 2.2 : 0)
  if ([90, 270].includes(((v.rotation % 360) + 360) % 360)) [w, h] = [h * (1000 / 1600), w * (1600 / 1000)]
  return direction === 'right' ? { dx: w + gap, dy: 0 } : { dx: 0, dy: h + gap }
}

/** The next free name like ``name``: its trailing number counted up past every name in use
 *  (PP-1 -> PP-2), or `` 2`` added. Case doesn't count, as on the server. */
export function nextName(name: string, used: string[]): string {
  const taken = new Set(used.map((u) => u.toLowerCase()))
  const m = /^(.*?)(\d+)$/.exec(name)
  const stem = m ? m[1] : `${name} `
  let n = m ? Number(m[2]) + 1 : 2
  const width = m ? m[2].length : 1
  while (taken.has(`${stem}${String(n).padStart(width, '0')}`.toLowerCase())) n++
  return `${stem}${String(n).padStart(width, '0')}`.slice(0, 40)
}

/** The next free SW-NN name for a switch made by hand. */
export function nextSwitchName(names: string[], made: number) {
  let n = made + 1
  const used = new Set(names.map((x) => x.toLowerCase()))
  while (used.has(`sw-${String(n).padStart(2, '0')}`)) n++
  return `SW-${String(n).padStart(2, '0')}`
}
