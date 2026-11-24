import type { ItemRef, Point } from './geometry'
import { type BlockRow, rowCount } from './rows'
import { nextFreeRow, nextName } from './tools'

/** An item as the server keeps it (positions in % of the plan), ready to be posted again. */
export interface Raw { kind: ItemRef['kind']; body: Record<string, unknown> }

// What a block needs to come back as it was.
export const BLOCK_FIELDS = ['name', 'x', 'y', 'rows', 'seat_width', 'seat_height', 'spacing_x', 'spacing_y', 'rotation',
  'reverse_numbers', 'naming', 'row_start', 'row_labels', 'seat_at', 'z']
// What a cable needs to be made again (floorbit/cables.py FIELDS).
export const CABLE_FIELDS = ['label', 'switch', 'port', 'panel', 'panel_port', 'seat', 'color', 'length_m', 'type', 'speed', 'note']
const MARK_SKIP = new Set(['id', 'hall_id'])

export function rawOf(kind: ItemRef['kind'], server: Record<string, unknown>): Raw {
  const keep = kind === 'block' ? BLOCK_FIELDS : kind === 'cable' ? CABLE_FIELDS : null
  const body = keep
    ? Object.fromEntries(keep.filter((k) => server[k] !== undefined).map((k) => [k, server[k]]))
    : Object.fromEntries(Object.entries(server).filter(([k]) => !MARK_SKIP.has(k)))
  return { kind, body }
}

const num = (v: unknown) => (typeof v === 'number' ? v : Number(v) || 0)
const round2 = (v: number) => Math.round(v * 100) / 100

/** Where an item sits, in %: a block's centre, a mark's anchor. */
export const rawAnchor = (r: Raw): Point => ({ x: num(r.body.x), y: num(r.body.y) })

function shifted(r: Raw, d: Point): Raw {
  const b: Record<string, unknown> = { ...r.body, x: round2(num(r.body.x) + d.x), y: round2(num(r.body.y) + d.y) }
  if (r.kind === 'mark' && r.body.kind === 'wall') {
    Object.assign(b, { x2: round2(num(r.body.x2) + d.x), y2: round2(num(r.body.y2) + d.y) })
    if (Array.isArray(r.body.points)) b.points = (r.body.points as [number, number][]).map(([x, y]) => [round2(x + d.x), round2(y + d.y)])
  }
  return { ...r, body: b }
}

/** Copies of ``items`` moved by ``d`` (in %). Seat blocks get the next free row letters (or block
 *  names) so their seats don't clash with the originals: the server refuses a seat twice. Patch
 *  panels and boards get the next free name. Cables aren't copied: a switch port has one cable. */
export function copies(items: Raw[], d: Point, blocksInUse: { naming?: string; row_start?: string; rows?: number | BlockRow[]; name?: string }[],
  panelsInUse: string[] = []): Raw[] {
  const used = [...blocksInUse]
  const names = [...panelsInUse]
  return items.filter((r) => r.kind !== 'cable').map((r) => {
    const out = shifted(r, d)
    if (r.kind === 'panel' || r.kind === 'board') {
      out.body.name = nextName(String(r.body.name ?? 'PP-1'), names)
      names.push(out.body.name as string)
      return out
    }
    if (r.kind !== 'block') return out
    const b = out.body
    const letter = nextFreeRow(used)
    if (b.naming === 'rows') b.row_start = letter
    else if (typeof b.name === 'string' && /^[A-Z]{1,2}$/i.test(b.name)) b.name = letter
    else if (typeof b.name === 'string' && b.name) b.name = `${b.name} 2`.slice(0, 40)
    used.push({ naming: b.naming as string, row_start: b.row_start as string, rows: rowCount(b.rows as number | BlockRow[]), name: b.name as string })
    return out
  })
}

/** The move that puts the first item's anchor at ``to`` (both in %). */
export function deltaTo(items: Raw[], to: Point): Point {
  if (!items.length) return { x: 0, y: 0 }
  const at = rawAnchor(items[0])
  return { x: to.x - at.x, y: to.y - at.y }
}
