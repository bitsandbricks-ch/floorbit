export interface PlanCell {
  x: number
  y: number
  seat: string
  hit: boolean
  on: boolean | null
  /** Row (its place in the block) and seat (its place in the row), from 0, for the editor's seat
   *  handles; missing on older answers. */
  rc?: [number, number]
  /** Degrees the seat is turned with its row (floorbit/seat_rows.py); missing on a straight row. */
  a?: number
  /** The side people sit on, of the way the row runs (left is up on a straight row); missing when not shown. */
  side?: 'left' | 'right'
  /** Where its seat cables run, across the row from the seat's centre (drawing units, in the block's
   *  own frame; floorbit/cable_lanes.py); missing when they come along the block instead. */
  lane?: number
  /** On a bent row with a lane: this seat's point in its row's lane (``PlanShape.lanes``). */
  li?: number
}

export interface PlanShape {
  /** The seat block's id, for the editor; missing on older answers. */
  id?: string
  cx: number
  cy: number
  rotation: number
  w: number
  h: number
  name: string
  cells: PlanCell[]
  /** Row letters (blocks named by row), in the block's own coordinates; missing on older answers. */
  rows?: { text: string; x: number; y: number; r?: number }[]
  /** Each row, top first (a cell's rc[0]): its id and name as /api/options/rows has them. Ids are
   *  the server's: never build one. Missing on older answers. */
  row_list?: { id: string; name: string; row?: string }[]
  /** The seats stand where the editor put them, not in rows (floorbit/seat_layout.py). */
  free?: boolean
  /** Bent rows' cable lanes by row (a cell's rc[0]): points in the block's own frame, drawing units,
   *  one past each end (floorbit/cable_lanes.py ``paths``). Missing when no row bends. */
  lanes?: Record<string, [number, number][]>
}

/** Text, walls, zones and icons on a hall (floorbit/plan_marks.py), in drawing units. */
/** Items of one hall the editor moves as one (floorbit/plan_groups.py). */
export interface PlanGroup {
  id: string
  hall_id?: string
  name: string
  members: { kind: 'block' | 'mark' | 'switch' | 'panel' | 'board'; id: string }[]
}

export interface PlanMark {
  id?: string
  kind: 'text' | 'icon' | 'wall' | 'walkway' | 'zone'
  /** Drawing order, higher on top (floorbit/stacking.py). */
  z?: number
  x: number
  y: number
  text?: string
  icon?: string
  size?: 's' | 'm' | 'l'
  /** Stretch on top of ``size`` for a label or icon (0.25 to 8; missing is 1). */
  scale?: number
  rotation?: number
  x2?: number
  y2?: number
  /** A wall's bends between its ends, [x, y] each (drawing units in the plan, % from /api/plan-marks). */
  points?: [number, number][]
  style?: 'solid' | 'dashed'
  /** A walkway's width, in seats (0.5 to 20; #1564). */
  width?: number
  w?: number
  h?: number
  label?: string
  color?: 'muted' | 'bit' | 'trace' | 'warn' | 'down'
  /** The floor plan layer it's on (floorbit/plan_marks.py LAYERS); overview when missing. */
  layer?: 'overview' | 'safety' | 'network' | 'electrical' | 'services'
  /** The crew's own colour, ``#rrggbb``; missing is the theme's. */
  tint?: string
}

export interface PlanDrawing {
  shapes: PlanShape[]
  box: string
  cell: number
  marks?: PlanMark[]
  /** The path data of the icons the marks use, by name (24 x 24, stroked). */
  icons?: Record<string, string[]>
  /** Uploaded icons the marks use, by id, as ``data:`` URIs (floorbit/icon_library.py). */
  custom_icons?: Record<string, string>
}
/** A switch login Floorbit keeps (issue #474): never the password. */
/** label: what pickers show: the name, or the row letters (C–D) of a block named by its rows. */
export interface SeatBlock { id: string; name: string; label: string; row_names: string[]; rows: { id: string; seats: number }[]; hall_id: string }
