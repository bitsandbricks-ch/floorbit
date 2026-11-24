import type { BlockRow } from './rows'
import type { Pt } from './rowShapes'

/** How many pieces a path row may have (floorbit/seat_rows.py MAX_PIECES). */
export const PIECES_MAX = 8

/** A path row's pieces in order, each with its points and seats; the first takes what the others
 *  leave over. A row without pieces is one piece. */
export function piecesOf(row: BlockRow): { path: Pt[]; seats: number }[] {
  const later = row.pieces ?? []
  const first = row.seats - later.reduce((a, p) => a + p.seats, 0)
  return [{ path: (row.path ?? [[0, 0], [first, 0]]) as Pt[], seats: first }, ...later.map((p) => ({ path: p.path as Pt[], seats: p.seats }))]
}

/** ``row`` with piece ``k``'s points replaced. */
export function withPiecePath(row: BlockRow, k: number, path: Pt[]): BlockRow {
  if (k === 0) return { ...row, path }
  return { ...row, pieces: (row.pieces ?? []).map((p, i) => (i === k - 1 ? { ...p, path } : p)) }
}

/** ``row`` with piece ``k`` (not the first) holding ``seats``; the first piece gives or takes them
 *  and keeps at least one. */
export function withPieceSeats(row: BlockRow, k: number, seats: number): BlockRow {
  if (k < 1 || !row.pieces?.[k - 1]) return row
  const others = row.pieces.reduce((a, p, i) => a + (i === k - 1 ? 0 : p.seats), 0)
  const n = Math.max(1, Math.min(Math.round(seats), row.seats - others - 1))
  return { ...row, pieces: row.pieces.map((p, i) => (i === k - 1 ? { ...p, seats: n } : p)) }
}

/** A new piece of ``seats`` seats (taken from the first piece), a straight line two seats below
 *  everything the row has so far, to drag into place on the plan. */
export function addPiece(row: BlockRow, seats = 4): BlockRow {
  const all = piecesOf(row)
  if (all.length >= PIECES_MAX || all[0].seats < 2) return row
  const n = Math.max(1, Math.min(seats, all[0].seats - 1))
  const pts = all.flatMap((p) => p.path)
  const left = Math.min(...pts.map((p) => p[0])), below = Math.max(...pts.map((p) => p[1])) + 2
  return { ...row, pieces: [...(row.pieces ?? []), { path: [[left, below], [left + n, below]], seats: n }] }
}

/** ``row`` without piece ``k`` (not the first); its seats go back to the first piece. */
export function dropPiece(row: BlockRow, k: number): BlockRow {
  if (k < 1) return row
  const pieces = (row.pieces ?? []).filter((_, i) => i !== k - 1)
  const out: BlockRow = { ...row, pieces }
  if (!pieces.length) delete out.pieces
  return out
}
