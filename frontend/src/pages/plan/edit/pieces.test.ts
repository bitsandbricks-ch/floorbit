import { describe, expect, it } from 'vitest'
import { addPiece, dropPiece, piecesOf, withPieceSeats } from './pieces'
import { rowSeats } from './rowShapes'
import { type BlockRow, withSeats, withShape } from './rows'

// Mike's row Z: 44 seats, a U opening downwards with a line of 10 inside it.
const z: BlockRow = {
  id: '1', seats: 44, shape: 'path', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [],
  path: [[0, 6], [0, 0], [20, 0], [20, 6]], pieces: [{ path: [[4, 4], [16, 4]], seats: 10 }],
}

describe('path rows in pieces', () => {
  it('runs the seats through the pieces, as floorbit/seat_rows.py does', () => {
    const seats = rowSeats(z)
    expect(seats).toHaveLength(44)
    expect(seats[0]).toEqual([0, 5.5])
    expect(seats[34]).toEqual([4.5, 4])
    expect(seats[43]).toEqual([13.5, 4])
    expect(piecesOf(z).map((p) => p.seats)).toEqual([34, 10])
  })

  it('gives seats to a piece from the first one, which keeps at least one', () => {
    expect(piecesOf(withPieceSeats(z, 1, 12)).map((p) => p.seats)).toEqual([32, 12])
    expect(piecesOf(withPieceSeats(z, 1, 99)).map((p) => p.seats)).toEqual([1, 43])
  })

  it('adds a piece below the others and takes one out again', () => {
    const more = addPiece(z, 4)
    expect(more.pieces).toHaveLength(2)
    expect(more.pieces![1]).toEqual({ path: [[0, 8], [4, 8]], seats: 4 })
    expect(dropPiece(more, 2).pieces).toEqual(z.pieces)
    expect(dropPiece(z, 1).pieces).toBeUndefined()
  })

  it('drops pieces that no longer fit when the row gets shorter, or stops being a path', () => {
    expect(withSeats(z, 20).pieces).toEqual(z.pieces)
    expect(withSeats(z, 10).pieces).toBeUndefined()
    expect(withShape(z, 'line').pieces).toBeUndefined()
  })
})
