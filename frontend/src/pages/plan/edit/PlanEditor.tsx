import { ActionIcon, Anchor, Badge, Button, ColorSwatch, Group, Kbd, Menu, NumberInput, Paper, SegmentedControl, Select, Stack, Tabs, Text, TextInput, Tooltip, UnstyledButton, VisuallyHidden } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import {
  IconArrowBackUp, IconArrowForwardUp, IconBookmark, IconBookmarks, IconHistory, IconClipboard, IconCopy, IconCut, IconLayersSubtract, IconLayoutAlignBottom, IconLayoutAlignCenter,
  IconLayoutAlignLeft, IconLayoutAlignMiddle, IconLayoutAlignRight, IconLayoutAlignTop, IconLayoutDistributeHorizontal, IconLayoutDistributeVertical,
  IconLink, IconLock, IconLockOpen, IconRotateClockwise, IconSelectAll, IconStack2, IconStackBack, IconStackFront, IconTrash, IconUnlink, IconZoomIn,
} from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type ComponentProps, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Attribution } from '@/components/Attribution'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { Cable, Circuit, PlanCable, PlanGroup, PlanMark, PlanShape, PowerMarkers, SeatViewData } from '@/api/types'
import { CableModal, type CableDraft } from '@/components/CableModal'
import { cablePath, useCablePlan } from '../cablePlan'
import { followPlan } from '../cableRoute'

import type { LayerState } from '../layers'
import type { Filter, View } from '../model'
import { SeatMap } from '../SeatMap'
import { BendHandles } from './BendHandles'
import { BlockFields } from './BlockFields'
import { nextItem } from './cycle'
import { ItemList } from './ItemList'
import { BackgroundFields, CalibrateFields } from './BackgroundFields'
import { BackgroundHandles } from './BackgroundHandles'
import { fitFactor, framePct, scaleFrame, seatMetres } from './background'
import { LockBadges } from './LockBadges'
import { Rulers } from './Rulers'
import { useSnapPrefs } from './snap'
import { MarkHandles } from './MarkHandles'
import { type BlockRow } from './rows'
import { SeatHandles } from './SeatHandles'
import { RowGapHandles } from './RowGapHandles'
import { RowLabelHandle } from './RowLabelHandle'
import { RowShapeHandles } from './RowShapeHandles'
import { keepTop, rowAt } from './rowGaps'
import { moveSeats, placedNow, toBlock } from './seatPlace'
import { RotateHandle } from './RotateHandle'
import { shapeBody } from './reshape'
import { SharedFields } from './SharedFields'
import { TintField } from './TintField'
import { hallIsEmpty } from './emptyHall'
import { EmptyHall, PlanDialogs, type PlanDialog } from './PlanMenu'
import { type PlanPreset, SavePresetDialog } from './Presets'
import { LAYER_IDS, type SharedField, ZONE_COLORS, sharedEdits, sharedFields } from './shared'
import { PlaceSwitchDialog, type SwitchPick } from './SwitchDialog'
import { type Route, bendsPct } from './bends'
import { EditOverlay } from './EditOverlay'
import { type Box, type ItemRef, type Point, allItems, fromPct, movePatch, moved, nearest, outlineOf, refKey, sameRef, seatAt, snappedDelta, toPct, wallCorners } from './geometry'
import { type CableEnds, type CableLook, CableFields, PanelFields, PlacePanelDialog } from './NetworkFields'
import { BoardFields, PlaceBoardDialog } from './PowerFields'
import { type NewBlock, PlaceBlockDialog, PlaceMarkDialog } from './PlaceDialogs'
import { type AreaBox, FillAreaDialog, type FillOptions } from './FillAreaDialog'
import { ToolRail } from './ToolRail'
import { canTurnOne, quarterTurns } from './turn'
import { frameOf } from './frame'
import { similar } from './similar'
import { TOOL_KEYS, TOOLS, type Tool } from './tools'
import { WalkwayFields } from './WalkwayFields'
import { isLine } from '../lineMarks'
import { useHistory } from './history'
import { type Raw, copies, deltaTo, rawOf } from './clipboard'
import { type AlignHow, type Guide, alignMoves, distributeMoves, groupsOf, regrouped, snapToGuides, withGroups } from './arrange'
import { PlanIconSelect } from './IconSelect'
import { PanelResize } from './PanelResize'
import { usePanelWidth } from './panelWidth'
import { blockName } from './blockName'
import { MergeBlocks, SplitBlock } from './BlockJoin'
import { useBlockJoin } from './useBlockJoin'

/** The bends a cable has of its own, also while it is drawn straight. */
const bendsOf = (c: PlanCable): [number, number][] => c.bends ?? c.points.slice(1, -1)

const PATH: Record<ItemRef['kind'], string> = {
  block: '/api/seat-blocks', mark: '/api/plan-marks', switch: '/api/switches', panel: '/api/cable-plan/panels', cable: '/api/cables',
  board: '/api/power/boards',
}
interface Saved { ref: ItemRef; raw: Raw }
const CLIP_KEY = 'floorbit-plan-clipboard'
// Copied items live here and in the browser's storage, so they paste into another hall or tab too.
let clipboard: Raw[] | null = null
function readClip(): Raw[] | null {
  try { return JSON.parse(localStorage.getItem(CLIP_KEY) ?? 'null') ?? clipboard } catch { return clipboard }
}
function writeClip(items: Raw[]) {
  clipboard = items
  try { localStorage.setItem(CLIP_KEY, JSON.stringify(items)) } catch { /* storage blocked: this tab still has it */ }
}
const NUDGE_PCT = 0.5

const typing = (el: EventTarget | null) => el instanceof HTMLElement && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))

/** The plan's Edit mode (in React; the older editor at ``/`` still has the tools not moved yet):
 *  select by click, Shift-click or a box, move by dragging or the arrow keys on the editor's grid,
 *  rename, turn and delete, with undo and redo. Every change is saved at once. */
export function PlanEditor({ data, view, setView, layers, refresh: refreshPlan, onHall, onShortcuts, startTool = 'select', onDone = () => {}, filter = 'all', live, dialog = null, onDialog = () => {} }: {
  data: SeatViewData; view: View; setView: (v: View) => void; layers: LayerState; refresh: () => Promise<unknown>
  /** Shows another hall, still editing. */
  onHall: (id: string) => void
  /** Opens the list of keys ("?" does too). */
  onShortcuts: () => void
  /** The tool picked on the live plan's rail, which opened the editor. */
  startTool?: Tool
  /** View on the rail: back to the live plan. */
  onDone?: () => void
  /** The live plan's filter and layers keep showing while the plan is changed. */
  filter?: Filter
  live?: Pick<ComponentProps<typeof SeatMap>, 'traffic' | 'firewalls' | 'wifi' | 'incidents'>
  /** What the top bar's Plan menu opened (PlanMenu.tsx). */
  dialog?: PlanDialog | null
  onDialog?: (d: PlanDialog | null) => void
}) {
  const { t } = useTranslation()
  const [selection, setSelection] = useState<ItemRef[]>([])
  const [drag, setDrag] = useState<{ d: Point } | null>(null)
  const [frozenPanel, setFrozenPanel] = useState<React.ReactNode>(null)
  // A move the server has saved but the plan hasn't fetched again yet: keep drawing it moved.
  const [pending, setPending] = useState<{ moves: [ItemRef, Point][]; data: SeatViewData } | null>(null)
  // A mark being resized with its handles: drawn as it is now, and after the drop until the plan comes back.
  const [shaping, setShaping] = useState<{ mark: PlanMark; data: SeatViewData; done?: boolean } | null>(null)
  // The rotate handle's angle while it is dragged, and after until the plan comes back with it.
  const [turning, setTurning] = useState<{ ref: ItemRef; deg: number; data: SeatViewData; done?: boolean } | null>(null)
  // The Measure tool's last line (for calibrating), and the background while it is being placed.
  const [measured, setMeasured] = useState<{ a: Point; b: Point } | null>(null)
  const [bgPlacing, setBgPlacing] = useState(false)
  // The seat block whose seats have handles, to be placed one by one (SeatHandles.tsx).
  const [arranging, setArranging] = useState<string | null>(null)
  const [bgDraft, setBgDraft] = useState<{ frame: Box; data: SeatViewData; done?: boolean } | null>(null)
  const [guides, setGuides] = useState<Guide[]>([])
  const [space, setSpace] = useState(false)
  const [tool, setTool] = useState<Tool>(startTool)
  // Where a click with the block, text or icon tool asked for something, while its dialog is open.
  // The box the Fill area tool just drew (in % of the plan), while its dialog is open (#1565).
  const [filling, setFilling] = useState<AreaBox | null>(null)
  const [placing, setPlacing] = useState<{ kind: 'block' | 'switch' | 'text' | 'icon' | 'panel' | 'board'; at: Point } | null>(null)
  // The cable form: a new cable (the Cable tool, filled with what was clicked) or one to change.
  const [cableForm, setCableForm] = useState<{ cable: Cable | null; initial?: Partial<CableDraft> } | null>(null)
  const small = useMediaQuery('(max-width: 48em)')
  const [menu, setMenu] = useState<{ item: ItemRef | null; x: number; y: number; at: Point | null } | null>(null)
  const history = useHistory()
  const qc = useQueryClient()
  // Cables and patch-panel use follow every change: ask for them again with the plan.
  const refresh = useCallback(() => Promise.all([
    refreshPlan(), qc.invalidateQueries({ queryKey: qk.cablePlan(data.hall) }), qc.invalidateQueries({ queryKey: qk.optionsAll }),
    // ['power'] covers the markers too; asking for both fetched the markers twice (#1301).
    qc.invalidateQueries({ queryKey: qk.power }),
    // A block's rows (the panel's list, the bars between rows) follow undo and redo too.
    qc.invalidateQueries({ queryKey: qk.planBlocks(data.hall) }),
  ]), [refreshPlan, qc, data.hall])
  /** After moving, turning, restacking (``shape`` false) or changing (``shape`` true) ``refs``: reads
   *  again only what that can change, not every query of the editor (#1301). The plan, and the power
   *  layer when a board moved; a block's rows when a block changed. A change to anything but blocks
   *  and marks (names, ports) reads everything. */
  const refreshFor = useCallback((refs: ItemRef[], shape = false): Promise<unknown> => {
    const kinds = new Set(refs.map((r) => r.kind))
    if (shape && [...kinds].some((k) => k !== 'block' && k !== 'mark')) return refresh()
    return Promise.all([
      refreshPlan(),
      kinds.has('board') ? qc.invalidateQueries({ queryKey: qk.power }) : null,
      shape && kinds.has('block') ? qc.invalidateQueries({ queryKey: qk.planBlocks(data.hall) }) : null,
    ])
  }, [refresh, refreshPlan, qc, data.hall])
  const groupsQ = useQuery({ queryKey: qk.planGroups(data.hall), queryFn: () => get<{ groups: PlanGroup[] }>(`/api/plan-groups?hall=${encodeURIComponent(data.hall)}`) })
  const groups = useMemo(() => groupsQ.data?.groups ?? [], [groupsQ.data])
  const saveGroups = useCallback(async (list: PlanGroup[]) => {
    await put('/api/plan-groups', { hall_id: data.hall, groups: list })
    await qc.invalidateQueries({ queryKey: qk.planGroups(data.hall) })
  }, [data.hall, qc])
  // Locked items (floorbit/plan_locks.py) stay where they are: moves, turns, handles and deletes skip them.
  const snapping = useSnapPrefs()
  const locksQ = useQuery({ queryKey: qk.planLocks(data.hall), queryFn: () => get<{ locks: ItemRef[] }>(`/api/plan-locks?hall=${encodeURIComponent(data.hall)}`) })
  const lockedKeys = useMemo(() => new Set((locksQ.data?.locks ?? []).map(refKey)), [locksQ.data])
  const isLocked = useCallback((r: ItemRef) => lockedKeys.has(refKey(r)), [lockedKeys])
  const unlocked = useCallback((items: ItemRef[]) => items.filter((r) => !lockedKeys.has(refKey(r))), [lockedKeys])
  // The power layer, so boards and what they feed show while they're placed and moved.
  const markers = useQuery({ queryKey: qk.powerMarkers, queryFn: () => get<PowerMarkers>('/api/power/markers'), staleTime: 30_000 })
  const cablePlan = useCablePlan(data.hall, true)
  const cables = useMemo(() => (cablePlan?.cables ?? []).filter((c) => c.kind === 'lan' && c.ref.cable), [cablePlan])
  // A deleted item comes back with a new id; steps recorded before still name the old one.
  const alias = useRef(new Map<string, string>())
  const idOf = useCallback((ref: ItemRef) => {
    let id = ref.id
    for (let i = 0; i < 20 && alias.current.has(`${ref.kind}:${id}`); i++) id = alias.current.get(`${ref.kind}:${id}`)!
    return id
  }, [])

  if (pending && pending.data !== data) setPending(null)
  if (shaping?.done && shaping.data !== data) setShaping(null)
  if (turning?.done && turning.data !== data) setTurning(null)
  if (bgDraft?.done && bgDraft.data !== data) setBgDraft(null)
  // Selected items that are gone (deleted elsewhere, another hall) drop out of the selection.
  const present = useMemo(() => [...allItems(data), ...cables.map((c) => ({ kind: 'cable' as const, id: c.ref.cable! }))], [data, cables])
  const selected = useMemo(() => selection.filter((r) => present.some((p) => sameRef(p, r))), [selection, present])
  // Phones and tablets, where the panel is under the plan: its bar folds it away to give the plan
  // the room. Picking something else opens it again, since its fields are what you want next.
  const under = useMediaQuery('(max-width: 1099.98px)')
  const selKey = selected.map(refKey).join(' ')
  // Phones start with the plan in full: the sheet comes up once something is picked.
  const [foldedAt, setFoldedAt] = useState<string | null>(() => (window.matchMedia?.('(max-width: 767.98px)').matches ? '' : null))
  const folded = !!under && foldedAt === selKey
  // The row picked in a seat block's panel, kept here so a double-click on the plan can pick one.
  const [pickedRow, setPickedRow] = useState<{ block: string; row: string } | null>(null)
  // The panel's tab (Mike picked tabs and sub tabs): Rows and Seats are there for one seat block.
  const [tab, setTab] = useState<PanelTab>('edit')
  const [panelWidth, setPanelWidth] = usePanelWidth()
  const oneBlock = selected.length === 1 && selected[0].kind === 'block' ? selected[0].id : null
  // The selected block as the server keeps it (its rows' spaces), shared with BlockFields.
  const storedBlocks = useQuery({
    queryKey: qk.planBlocks(data.hall), enabled: !!oneBlock,
    queryFn: () => get<{ id: string; rows: BlockRow[]; seat_at?: unknown }[]>(`/api/seat-blocks?hall=${encodeURIComponent(data.hall)}`),
  })

  const shown = useMemo(() => {
    let d = data
    if (pending) for (const [r, m] of pending.moves) d = moved(d, [r], m)
    if (drag) d = moved(d, unlocked(selected), drag.d)
    if (shaping && d.drawing) {
      const marks = d.drawing.marks?.map((m) => (m.id === shaping.mark.id ? shaping.mark : m))
      d = { ...d, drawing: { ...d.drawing, marks } }
    }
    if (turning && d.drawing) {
      const { ref, deg } = turning
      const shapes = d.drawing.shapes.map((b) => (ref.kind === 'block' && b.id === ref.id ? { ...b, rotation: deg } : b))
      const marks = d.drawing.marks?.map((m) => (ref.kind === 'mark' && m.id === ref.id ? { ...m, rotation: deg } : m))
      d = { ...d, drawing: { ...d.drawing, shapes, marks } }
    }
    if (bgDraft) d = { ...d, background_frame: bgDraft.frame }
    return d
  }, [data, pending, drag, selected, shaping, turning, unlocked, bgDraft])

  // Boards drawn where the editor has them (dragged or just moved), not where the markers last said.
  const power = useMemo(() => {
    const m = markers.data
    if (!m?.enabled) return undefined
    const at = new Map((shown.boards ?? []).map((b) => [b.id, toPct(shown.size, b)]))
    return { ...m, boards: m.boards.map((b) => (at.has(b.id) ? { ...b, ...at.get(b.id)! } : b)) }
  }, [markers.data, shown])

  const fail = useCallback((err: unknown) => {
    notifications.show({ color: 'down', title: t('plan.edit.failed'), message: err instanceof Error ? err.message : String(err) })
  }, [t])
  const join = useBlockJoin({ hall: data.hall, push: history.push, refresh, fail, select: setSelection, idOf, alias })

  const setLocked = useCallback(async (items: ItemRef[], locked: boolean) => {
    const refs = items.filter((r) => r.kind !== 'cable' && lockedKeys.has(refKey(r)) !== locked)
    if (!refs.length) return
    const save = (on: boolean) => put('/api/plan-locks', { hall_id: data.hall, items: refs, locked: on })
      .then(() => qc.invalidateQueries({ queryKey: qk.planLocks(data.hall) }))
    try {
      await save(locked)
      history.push({ label: t(locked ? 'plan.edit.step.lock' : 'plan.edit.step.unlock', { count: refs.length }), undo: () => save(!locked), redo: () => save(locked) })
    } catch (err) {
      fail(err)
    }
  }, [data.hall, lockedKeys, qc, history, t, fail])

  // Boards and cables change with PATCH, the plan's own items with PUT.
  const send = useCallback(async (ref: ItemRef, body: Record<string, unknown>) =>
    (ref.kind === 'board' ? patch : put)(`${PATH[ref.kind]}/${encodeURIComponent(idOf(ref))}`, body), [idOf])

  /** Moves each item by its own amount (drawing units), saved at once, as one step to undo. */
  const moveEach = useCallback(async (moves: [ItemRef, Point][], label?: string) => {
    moves = moves.filter(([r, d]) => (d.x || d.y) && !isLocked(r))
    if (!moves.length) return
    const there = moves.map(([r, d]) => [r, movePatch(data, r, d), movePatch(data, r, { x: 0, y: 0 })] as const).filter(([, a, b]) => a && b)
    setPending({ moves, data })
    try {
      await Promise.all(there.map(([r, a]) => send(r, a!)))
      history.push({
        label: label ?? t('plan.edit.step.move', { count: there.length }),
        undo: () => Promise.all(there.map(([r, , b]) => send(r, b!))).then(() => refreshFor(moves.map(([r]) => r))),
        redo: () => Promise.all(there.map(([r, a]) => send(r, a!))).then(() => refreshFor(moves.map(([r]) => r))),
      })
    } catch (err) {
      setPending(null)
      fail(err)
    }
    await refreshFor(moves.map(([r]) => r))
  }, [data, send, history, t, refreshFor, fail, isLocked])
  const moveBy = useCallback((items: ItemRef[], d: Point) => moveEach(items.map((r) => [r, d] as [ItemRef, Point])), [moveEach])

  /** Puts the selected items in one new group (``join``) or takes them out of theirs. */
  const regroup = useCallback(async (items: ItemRef[], join: boolean) => {
    const all = withGroups(items, groups).filter((r) => r.kind !== 'cable')
    if (join ? all.length < 2 : !groupsOf(groups, all).length) return
    let n = groups.length + 1
    while (groups.some((g) => g.name === t('plan.edit.groups.name', { n }))) n++
    const made = join ? { id: `g-${Math.random().toString(36).slice(2, 10)}`, name: t('plan.edit.groups.name', { n }) } : undefined
    const before = groups, after = regrouped(groups, all, made)
    try {
      await saveGroups(after)
      history.push({
        label: t(join ? 'plan.edit.step.group' : 'plan.edit.step.ungroup'),
        undo: () => saveGroups(before),
        redo: () => saveGroups(after),
      })
    } catch (err) {
      fail(err)
    }
  }, [groups, saveGroups, history, t, fail])

  const renameGroup = useCallback(async (group: PlanGroup, name: string) => {
    const before = groups, after = groups.map((g) => (g.id === group.id ? { ...g, name } : g))
    try {
      await saveGroups(after)
      history.push({ label: t('plan.edit.step.renameGroup'), undo: () => saveGroups(before), redo: () => saveGroups(after) })
    } catch (err) {
      fail(err)
    }
  }, [groups, saveGroups, history, t, fail])

  /** The items as the server keeps them, to copy, delete with undo, or restack. */
  const snapshot = useCallback(async (items: ItemRef[]): Promise<Saved[]> => {
    const want = items
    const hall = encodeURIComponent(data.hall)
    const some = (k: ItemRef['kind']) => want.some((r) => r.kind === k)
    const none = Promise.resolve([] as Record<string, unknown>[])
    const [blocks, marks, panels, cableRows, boards, switchRows] = await Promise.all([
      some('block') ? get<Record<string, unknown>[]>(`/api/seat-blocks?hall=${hall}`) : none,
      some('mark') ? get<{ marks: Record<string, unknown>[] }>(`/api/plan-marks?hall=${hall}`).then((m) => m.marks) : none,
      some('panel') ? get<{ panels: Record<string, unknown>[] }>(`/api/cable-plan?hall=${hall}`).then((m) => m.panels.map((p) => ({ ...p, id: p.name }))) : none,
      some('cable') ? get<{ cables: Record<string, unknown>[] }>('/api/cables').then((m) => m.cables) : none,
      some('board') ? get<{ boards: Record<string, unknown>[] }>('/api/power').then((m) => m.boards) : none,
      some('switch') ? get<Record<string, unknown>[]>('/api/switches') : none,
    ])
    const rows = { block: blocks, mark: marks, panel: panels, cable: cableRows, board: boards, switch: switchRows }
    return want.map((r): Saved | null => {
      const raw = rows[r.kind].find((x) => String(x.id).toLowerCase() === idOf(r).toLowerCase())
      return raw ? { ref: r, raw: rawOf(r.kind, raw) } : null
    }).filter((x): x is Saved => !!x)
  }, [data.hall, idOf])

  const remove = useCallback(async (items: ItemRef[]) => {
    items = items.filter((r) => !isLocked(r))
    if (!items.length) return
    try {
      const saved = await snapshot(items)
      const drop = (s: Saved[]) => Promise.all(s.map(({ ref }) => del(`${PATH[ref.kind]}/${encodeURIComponent(idOf(ref))}`)))
      const restore = (s: Saved[]) => Promise.all(s.map(async ({ ref, raw }) => {
        // An inventory switch only left the plan: put it back where it was.
        if (ref.kind === 'switch' && raw.body.source !== 'manual') {
          await put(`${PATH.switch}/${encodeURIComponent(idOf(ref))}`, { x: raw.body.x, y: raw.body.y, hall_id: data.hall })
          return
        }
        const made = await post<{ id: string }>(PATH[ref.kind], { ...raw.body, hall_id: data.hall })
        alias.current.set(`${ref.kind}:${idOf(ref)}`, made.id)
      }))
      await drop(saved)
      setSelection([])
      history.push({
        label: t('plan.edit.step.delete', { count: saved.length }),
        undo: () => restore(saved).then(refresh),
        redo: () => drop(saved).then(refresh),
      })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [data.hall, idOf, history, t, refresh, fail, snapshot, isLocked])

  /** Posts ``raws`` as new items in this hall (paste, duplicate), selects them, with undo. */
  const addRaws = useCallback(async (raws: Raw[], label: string) => {
    if (!raws.length) return
    const post1 = async (r: Raw) => ({ kind: r.kind, id: (await post<{ id: string }>(PATH[r.kind], { ...r.body, hall_id: data.hall })).id })
    try {
      // One by one: the server checks each block's seats against the ones already there.
      const made: ItemRef[] = []
      for (const r of raws) made.push(await post1(r))
      history.push({
        label,
        undo: () => Promise.all(made.map((r) => del(`${PATH[r.kind]}/${encodeURIComponent(idOf(r))}`))).then(refresh),
        redo: async () => {
          for (const [i, r] of raws.entries()) {
            const again = await post1(r)
            alias.current.set(`${r.kind}:${idOf(made[i])}`, again.id)
          }
          await refresh()
        },
      })
      await refresh()
      void qc.invalidateQueries({ queryKey: qk.seatBlocks })
      setSelection(made)
    } catch (err) {
      fail(err)
      await refresh()
    }
  }, [data.hall, history, idOf, refresh, fail, qc])

  const blocksInUse = useCallback(() => get<{ naming?: string; row_start?: string; rows?: number | BlockRow[]; name?: string }[]>('/api/seat-blocks'), [])
  // Names copies of panels and boards must not take (both kinds go through one list).
  const panelsInUse = useCallback(() => get<{ options: { value: string }[] }>('/api/options/panels')
    .then((o) => [...o.options.map((x) => x.value), ...(markers.data?.boards ?? []).map((b) => b.name)]), [markers.data])

  const copy = useCallback(async (items: ItemRef[], cut = false) => {
    try {
      // A switch port has one cable: cables aren't copied (cut still removes them).
      const saved = (await snapshot(items)).filter((s) => s.ref.kind !== 'cable' && s.ref.kind !== 'switch')
      if (!saved.length) return
      writeClip(saved.map((s) => s.raw))
      notifications.show({ message: t(cut ? 'plan.edit.cut' : 'plan.edit.copied', { count: saved.length }), autoClose: 1500 })
      if (cut) await remove(items)
    } catch (err) {
      fail(err)
    }
  }, [snapshot, remove, t, fail])

  // Where the pointer last was over the plan, in %: paste puts things there.
  const pointer = useRef<Point | null>(null)
  const paste = useCallback(async (at?: Point) => {
    const clip = readClip()
    if (!clip?.length) return
    const to = at ?? pointer.current
    const d = to ? deltaTo(clip, to) : { x: 2, y: 3.2 }
    await addRaws(copies(clip, d, await blocksInUse(), await panelsInUse()), t('plan.edit.step.paste', { count: clip.length }))
  }, [addRaws, blocksInUse, panelsInUse, t])

  // A preset placed from the right-click menu goes where it was opened, from the Plan menu where the pointer last was.
  const presetAt = useRef<Point | null>(null)
  const [presetDraft, setPresetDraft] = useState<Raw[] | null>(null)
  const saveAsPreset = useCallback(async (items: ItemRef[]) => {
    try {
      // As copy: a switch is one device and a switch port has one cable.
      const saved = (await snapshot(items)).filter((s) => s.ref.kind !== 'cable' && s.ref.kind !== 'switch')
      if (saved.length) setPresetDraft(saved.map((s) => s.raw))
    } catch (err) {
      fail(err)
    }
  }, [snapshot, fail])
  const placePreset = useCallback(async (p: PlanPreset) => {
    const to = presetAt.current ?? pointer.current
    presetAt.current = null
    const d = to ? deltaTo(p.items, to) : { x: 0, y: 0 }
    try {
      await addRaws(copies(p.items, d, await blocksInUse(), await panelsInUse()), t('presets.step', { name: p.name }))
    } catch (err) {
      fail(err)
    }
  }, [addRaws, blocksInUse, panelsInUse, t, fail])

  const duplicate = useCallback(async (items: ItemRef[]) => {
    try {
      const saved = (await snapshot(items)).filter((s) => s.ref.kind !== 'switch')
      // One seat further right and down, so the copy shows next to the original.
      const raws = copies(saved.map((s) => s.raw), { x: 2, y: 3.2 }, await blocksInUse(), await panelsInUse())
      await addRaws(raws, t('plan.edit.step.duplicate', { count: raws.length }))
    } catch (err) {
      fail(err)
    }
  }, [snapshot, addRaws, blocksInUse, panelsInUse, t, fail])

  /** Bring to front (``up``) or send to back: the items' z goes past every other item's. */
  const restack = useCallback(async (items: ItemRef[], up: boolean) => {
    try {
      // Only blocks and marks stack; switches and patch panels are always on top.
      const all = await snapshot(present.filter((r) => r.kind === 'block' || r.kind === 'mark'))
      const mine = all.filter((s) => items.some((r) => sameRef(r, s.ref)))
      if (!mine.length) return
      const zs = all.filter((s) => !mine.includes(s)).map((s) => Number(s.raw.body.z) || 0)
      const edge = zs.length ? (up ? Math.max(...zs) + 1 : Math.min(...zs) - 1) : 0
      const moves = mine.map((s, i) => [s.ref, { z: Number(s.raw.body.z) || 0 }, { z: up ? edge + i : edge - (mine.length - 1 - i) }] as const)
      await Promise.all(moves.map(([r, , a]) => send(r, a)))
      history.push({
        label: t(up ? 'plan.edit.step.front' : 'plan.edit.step.back'),
        undo: () => Promise.all(moves.map(([r, b]) => send(r, b))).then(() => refreshFor(items)),
        redo: () => Promise.all(moves.map(([r, , a]) => send(r, a))).then(() => refreshFor(items)),
      })
    } catch (err) {
      fail(err)
    }
    await refreshFor(items)
  }, [snapshot, present, send, history, t, refreshFor, fail])

  /** R turns the selected blocks, labels and icons a quarter turn each, in place (Shift+R back). */
  const rotate = useCallback(async (items: ItemRef[], back: boolean) => {
    const turns = quarterTurns(data, items.filter((r) => !isLocked(r)), back)
    if (!turns.length) return
    try {
      await Promise.all(turns.map(([r, , a]) => send(r, a)))
      history.push({
        label: t('plan.edit.step.rotate', { count: turns.length }),
        undo: () => Promise.all(turns.map(([r, b]) => send(r, b))).then(() => refreshFor(turns.map(([r]) => r))),
        redo: () => Promise.all(turns.map(([r, , a]) => send(r, a))).then(() => refreshFor(turns.map(([r]) => r))),
      })
    } catch (err) {
      fail(err)
    }
    await refreshFor(turns.map(([r]) => r))
  }, [data, send, history, t, refreshFor, fail, isLocked])

  /** Gives every selected item that has ``field`` the same value, as one step to undo. Locked items
   *  keep their angle. */
  const changeAll = useCallback(async (items: ItemRef[], field: SharedField, value: unknown) => {
    const edits = sharedEdits(data, field === 'rotation' ? items.filter((r) => !isLocked(r)) : items, field, value)
    if (!edits.length) return
    try {
      await Promise.all(edits.map(([r, , a]) => send(r, a)))
      history.push({
        label: t('plan.edit.step.changeAll', { count: edits.length }),
        undo: () => Promise.all(edits.map(([r, b]) => send(r, b))).then(() => refreshFor(edits.map(([r]) => r), true)),
        redo: () => Promise.all(edits.map(([r, , a]) => send(r, a))).then(() => refreshFor(edits.map(([r]) => r), true)),
      })
    } catch (err) {
      fail(err)
    }
    await refreshFor(edits.map(([r]) => r), true)
  }, [data, send, history, t, refreshFor, fail, isLocked])

  /** Changes the hall itself (its background's place, its scale), as one step to undo. */
  const changeHall = useCallback(async (path: 'background' | 'scale', before: Record<string, unknown>, after: Record<string, unknown>, label: string) => {
    const url = `/api/halls/${encodeURIComponent(data.hall)}/${path}`
    const save = (body: Record<string, unknown>) => (path === 'background' ? patch(url, body) : put(url, body))
    try {
      await save(after)
      history.push({ label, undo: () => save(before).then(refresh), redo: () => save(after).then(refresh) })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [data.hall, history, refresh, fail])
  const bgFrame: Box = data.background_frame ?? { x: 0, y: 0, w: data.size.w, h: data.size.h }
  const placeBackground = (frame: Box | null) => {
    setBgDraft(frame ? { frame, data, done: true } : null)
    void changeHall('background', { frame: framePct(bgFrame, data.size) }, { frame: frame ? framePct(frame, data.size) : null }, t('plan.edit.step.background'))
  }

  const change = useCallback(async (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => {
    try {
      await send(ref, after)
      history.push({
        label: t('plan.edit.step.change'),
        undo: () => send(ref, before).then(() => refreshFor([ref], true)),
        redo: () => send(ref, after).then(() => refreshFor([ref], true)),
      })
    } catch (err) {
      fail(err)
    }
    await refreshFor([ref], true)
  }, [send, history, t, refreshFor, fail])

  /** The space above row ``i`` dragged to ``gap`` seats: the rows above stay where they are. */
  const moveGap = (ref: ItemRef, shape: PlanShape, rows: BlockRow[], i: number, gap: number) => {
    const cell = data.drawing?.cell ?? 32
    setPickedRow({ block: ref.id, row: rows[i].id })
    return change(ref, { rows, ...keepTop(shape, cell, data.size, 0) },
      { rows: rows.map((r, k) => (k === i ? { ...r, gap } : r)), ...keepTop(shape, cell, data.size, gap - rows[i].gap) })
  }

  /** Row ``i`` reshaped on the plan, the block moved to ``place`` so the row's anchor seat stays put. */
  const reshapeRow = (ref: ItemRef, shape: PlanShape, rows: BlockRow[], i: number, row: BlockRow, place: { x: number; y: number }) => change(ref,
    { rows, ...keepTop(shape, data.drawing?.cell ?? 32, data.size, 0) }, { rows: rows.map((r, k) => (k === i ? row : r)), ...place })

  /** A double click on a seat block picks the row under the pointer in its panel. */
  const pickRowAt = (ref: ItemRef, at: Point) => {
    if (ref.kind !== 'block') return
    const shape = data.drawing?.shapes.find((s) => s.id === ref.id)
    const cell = data.drawing?.cell ?? 32
    const i = shape ? rowAt(shape, cell, toBlock(shape, cell, at)) : null
    const id = i != null ? shape?.row_list?.[i]?.row : undefined
    if (!id) return
    setSelection([ref])
    setPickedRow({ block: ref.id, row: id })
    setTab('rows')
  }

  const pct = useCallback((p: Point) => { const v = toPct(data.size, p); return { x: Math.round(v.x * 100) / 100, y: Math.round(v.y * 100) / 100 } }, [data.size])

  /** New items from one request (a block, ``count`` blocks, a mark), with undo and redo. */
  const create = useCallback(async (kind: ItemRef['kind'], path: string, body: Record<string, unknown>, label: string) => {
    try {
      const out = await post<{ id: string } | { id: string }[]>(path, { ...body, hall_id: data.hall })
      let made: ItemRef[] = (Array.isArray(out) ? out : [out]).map((x) => ({ kind, id: x.id }))
      history.push({
        label,
        undo: () => Promise.all(made.map((r) => del(`${PATH[kind]}/${encodeURIComponent(idOf(r))}`))).then(refresh),
        redo: async () => {
          const again = await post<{ id: string } | { id: string }[]>(path, { ...body, hall_id: data.hall })
          const list = Array.isArray(again) ? again : [again]
          made.forEach((r, i) => { if (list[i]) alias.current.set(`${kind}:${idOf(r)}`, list[i].id) })
          made = made.map((r) => ({ ...r }))
          await refresh()
        },
      })
      await refresh()
      if (kind === 'block') void qc.invalidateQueries({ queryKey: qk.seatBlocks })
      return made
    } catch (err) {
      fail(err)
      return []
    }
  }, [data.hall, history, idOf, refresh, fail, qc])

  const placeBlock = useCallback(async (block: NewBlock, copies: { count: number; dx: number; dy: number } | null) => {
    if (!placing) return
    const at = pct(placing.at)
    const made = copies
      ? await create('block', '/api/seat-blocks/many', { ...block, ...at, ...copies }, t('plan.edit.step.addBlocks', { count: copies.count }))
      : await create('block', '/api/seat-blocks', { ...block, ...at }, t('plan.edit.step.addBlock'))
    if (made.length) setPlacing(null)
  }, [placing, pct, create, t])

  const placeMark = useCallback(async (body: Record<string, unknown>) => {
    if (!placing) return
    const made = await create('mark', '/api/plan-marks', { ...body, ...pct(placing.at) }, t(`plan.edit.step.add.${body.kind}`))
    if (made.length) setPlacing(null)
  }, [placing, pct, create, t])

  const placePanel = useCallback(async (body: { name: string; ports: number }) => {
    if (!placing) return false
    const made = await create('panel', PATH.panel, { ...body, ...pct(placing.at) }, t('plan.edit.step.addPanel', { name: body.name }))
    if (made.length) setPlacing(null)
    return made.length > 0
  }, [placing, pct, create, t])

  const placeBoard = useCallback(async (body: { name: string; location: string }) => {
    if (!placing) return false
    const made = await create('board', PATH.board, { ...body, ...pct(placing.at) }, t('plan.edit.step.addBoard', { name: body.name }))
    if (made.length) { setPlacing(null); setTool('select'); setSelection(made) }
    return made.length > 0
  }, [placing, pct, create, t])

  /** Switches from the inventory where the Switch tool was clicked (several in a small grid around
   *  it, as the older editor did), or one made by hand. */
  const placeSwitches = useCallback(async (pick: SwitchPick) => {
    if (!placing) return false
    const at = pct(placing.at)
    if ('name' in pick) {
      const made = await create('switch', PATH.switch, { name: pick.name, ...at }, t('plan.edit.step.addSwitch', { name: pick.name }))
      if (made.length) setPlacing(null)
      return made.length > 0
    }
    const cols = Math.ceil(Math.sqrt(pick.ids.length)), rows = Math.ceil(pick.ids.length / cols)
    const spots = pick.ids.map((id, i) => ({
      id, x: Math.round((at.x + ((i % cols) - (cols - 1) / 2) * 4) * 100) / 100, y: Math.round((at.y + (Math.floor(i / cols) - (rows - 1) / 2) * 6) * 100) / 100,
    }))
    const place = () => Promise.all(spots.map((s) => put(`${PATH.switch}/${encodeURIComponent(s.id)}`, { x: s.x, y: s.y, hall_id: data.hall })))
    try {
      await place()
      history.push({
        label: t('plan.edit.step.placeSwitch', { count: spots.length }),
        undo: () => Promise.all(spots.map((s) => del(`${PATH.switch}/${encodeURIComponent(s.id)}`))).then(refresh),
        redo: () => place().then(refresh),
      })
      setPlacing(null)
      setSelection(spots.map((s) => ({ kind: 'switch' as const, id: s.id })))
    } catch (err) {
      fail(err)
    }
    await refresh()
    void qc.invalidateQueries({ queryKey: qk.switches })
    return true
  }, [placing, pct, create, t, data.hall, history, refresh, fail, qc])

  /** A new circuit on ``board``, with undo. */
  const addCircuit = useCallback(async (board: string, name: string) => {
    try {
      let made = await post<Circuit>('/api/power/circuits', { board, name })
      history.push({
        label: t('plan.edit.step.addCircuit', { name }),
        undo: () => del(`/api/power/circuits/${encodeURIComponent(made.id)}`).then(refresh),
        redo: async () => { made = await post<Circuit>('/api/power/circuits', { board, name }); await refresh() },
      })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [history, t, refresh, fail])

  /** The selected seat blocks (whole) and switches go on ``circuit``, with undo. */
  const feed = useCallback(async (circuit: Circuit, items: ItemRef[]) => {
    const before = { blocks: circuit.blocks, switches: circuit.switches }
    const blocks = [...circuit.blocks.filter((b) => !items.some((r) => r.kind === 'block' && r.id === b.block)),
      ...items.filter((r) => r.kind === 'block').map((r) => ({ block: r.id, rows: [] as number[] }))]
    const after = { blocks, switches: [...new Set([...circuit.switches, ...items.filter((r) => r.kind === 'switch').map((r) => r.id)])] }
    const to = (body: typeof before) => patch(`/api/power/circuits/${encodeURIComponent(circuit.id)}`, body)
    try {
      await to(after)
      history.push({ label: t('plan.edit.step.feed', { name: circuit.name }), undo: () => to(before).then(refresh), redo: () => to(after).then(refresh) })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [history, t, refresh, fail])

  /** The Cable tool: the form, filled with the seat, switch or patch panel that was clicked. */
  const startCable = (raw: Point) => {
    const sw = nearest(data.switches, raw, 24), panel = nearest(data.panels ?? [], raw, 24)
    const seat = seatAt(data, raw) ?? ''
    // A seat the port watch already found on a switch port: start from that port, to keep it as a cable.
    const learned = seat ? cablePlan?.cables.find((c) => c.kind === 'lan' && !c.ref.cable && c.ref.seat === seat) : undefined
    setCableForm({ cable: null, initial: { seat, switch: sw?.name ?? learned?.ref.switch ?? '', port: sw ? '' : learned?.ref.port ?? '', panel: panel?.name ?? '' } })
  }
  const editCable = async (id: string) => {
    try {
      const cable = (await get<{ cables: Cable[] }>('/api/cables')).cables.find((c) => c.id === id)
      if (cable) setCableForm({ cable })
    } catch (err) {
      fail(err)
    }
  }
  /** What the cable form did, as a step to undo. */
  const cableDone = useCallback(async ({ saved, removed, before }: { saved?: Cable; removed?: Cable; before?: Cable | null }) => {
    setCableForm(null)
    const body = (c: Cable) => rawOf('cable', c as unknown as Record<string, unknown>).body
    const ref = (c: Cable): ItemRef => ({ kind: 'cable', id: c.id })
    const again = async (c: Cable) => {
      const made = await post<Cable>(PATH.cable, body(c))
      alias.current.set(`cable:${idOf(ref(c))}`, made.id)
    }
    const gone = (c: Cable) => del(`${PATH.cable}/${encodeURIComponent(idOf(ref(c)))}`)
    if (removed) {
      setSelection([])
      history.push({ label: t('plan.edit.step.deleteCable'), undo: () => again(removed).then(refresh), redo: () => gone(removed).then(refresh) })
    } else if (saved && before) {
      const to = (c: Cable) => patch(`${PATH.cable}/${encodeURIComponent(idOf(ref(saved)))}`, body(c))
      history.push({ label: t('plan.edit.step.changeCable'), undo: () => to(before).then(refresh), redo: () => to(saved).then(refresh) })
    } else if (saved) {
      history.push({ label: t('plan.edit.step.addCable'), undo: () => gone(saved).then(refresh), redo: () => again(saved).then(refresh) })
      setSelection([ref(saved)])
    }
    await refresh()
  }, [history, idOf, refresh, t])
  /** A cable moved to another switch port or seat from the side panel, as a step to undo. */
  const changeEnds = async (id: string, change: CableEnds) => {
    try {
      const before = (await get<{ cables: Cable[] }>('/api/cables')).cables.find((c) => c.id === id)
      if (!before) return
      const saved = await patch<Cable>(`/api/cables/${encodeURIComponent(id)}`, change)
      await cableDone({ saved, before })
    } catch (err) {
      fail(err)
    }
  }

  /** A cable's drawing: its bends (null: the automatic route) and corners, with undo. */
  const setRoute = useCallback(async (cable: PlanCable, after: { points: [number, number][] | null; corners: CableLook }, label: string) => {
    const before = cable.manual ? { points: bendsOf(cable), corners: cable.corners }
      : cable.drawn ? { points: null, corners: cable.corners } : null
    const to = (value: typeof after | null) => put('/api/cable-plan/routes', { routes: { [cable.key]: value } })
    try {
      await to(after)
      history.push({ label, undo: () => to(before).then(refresh), redo: () => to(after).then(refresh) })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [history, refresh, fail])

  const drawLine = (a: Point, b: Point) => {
    const p = pct(a), q = pct(b)
    const kind = tool === 'walkway' ? 'walkway' : 'wall'
    void create('mark', '/api/plan-marks', { kind, x: p.x, y: p.y, x2: q.x, y2: q.y }, t(`plan.edit.step.add.${kind}`))
  }
  const fillArea = async (opts: FillOptions) => {
    if (!filling) return false
    let n = groups.length + 1
    while (groups.some((g) => g.name === t('fillArea.group', { n }))) n++
    type Filled = { blocks: { id: string }[]; marks: { id: string }[]; group: { id: string } | null }
    const body = { ...filling, ...opts, hall_id: data.hall, group: t('fillArea.group', { n }) }
    const refsOf = (out: Filled): ItemRef[] => [...out.blocks.map((b) => ({ kind: 'block' as const, id: b.id })), ...out.marks.map((m) => ({ kind: 'mark' as const, id: m.id }))]
    const after = async () => {
      await refresh()
      void qc.invalidateQueries({ queryKey: qk.seatBlocks })
      void qc.invalidateQueries({ queryKey: qk.planGroups(data.hall) })
    }
    try {
      const out = await post<Filled>('/api/seat-blocks/fill', body)
      const made = refsOf(out)
      let group = out.group?.id
      history.push({
        label: t('fillArea.step', { count: out.blocks.length }),
        // Undo takes the runs, walkways and their group away; redo lays them out again, with new ids.
        undo: async () => {
          await Promise.all(made.map((r) => del(`${PATH[r.kind]}/${encodeURIComponent(idOf(r))}`)))
          if (group) await del(`/api/plan-groups/${encodeURIComponent(group)}`)
          await after()
        },
        redo: async () => {
          const again = await post<Filled>('/api/seat-blocks/fill', body)
          refsOf(again).forEach((r, i) => { if (made[i]) alias.current.set(`${r.kind}:${idOf(made[i])}`, r.id) })
          group = again.group?.id
          await after()
        },
      })
      await after()
      setFilling(null)
      setTool('select')
      setSelection(made)
      return true
    } catch (err) {
      fail(err)
      return false
    }
  }
  const drawZone = async (box: Box) => {
    const p = pct(box), size = toPct(data.size, { x: box.w, y: box.h })
    const made = await create('mark', '/api/plan-marks', { kind: 'zone', ...p, w: Math.round(size.x * 100) / 100, h: Math.round(size.y * 100) / 100 },
      t('plan.edit.step.add.zone'))
    // A new zone usually gets a name next: select it so the panel shows its label field.
    if (made.length) { setTool('select'); setSelection(made) }
  }

  /** A click in the history list: back to before a done step, or forward through an undone one. */
  const jump = useCallback(async (way: 'undo' | 'redo', count: number) => {
    try {
      const done = await history.jump(way, count)
      if (done) notifications.show({ message: t(`plan.edit.${way}ne`, { what: done.label }), autoClose: 1500 })
    } catch (err) {
      fail(err)
    }
  }, [history, t, fail])

  const step = useCallback(async (way: 'undo' | 'redo') => {
    try {
      const done = await history[way]()
      if (done) notifications.show({ message: t(`plan.edit.${way}ne`, { what: done.label }), autoClose: 1500 })
    } catch (err) {
      fail(err)
    }
  }, [history, t, fail])

  const onKey = (e: React.KeyboardEvent) => {
    if (typing(e.target)) return
    const mod = e.ctrlKey || e.metaKey
    const k = e.key.toLowerCase()
    const take = () => { e.preventDefault(); e.stopPropagation() }
    if (mod && k === 'z') { take(); void step(e.shiftKey ? 'redo' : 'undo'); return }
    if (mod && k === 'y') { take(); void step('redo'); return }
    if (mod && k === 'a' && e.shiftKey) { take(); if (selected.length) setSelection(similar(data, present, selected)); return }
    if (mod && k === 'a') { take(); setSelection(present); return }
    if (mod && k === 'g') { take(); void regroup(selected, !e.shiftKey); return }
    if (mod && k === 'v') { take(); void paste(); return }
    if (mod && selected.length && k === 'c') { take(); void copy(selected); return }
    if (mod && selected.length && k === 'x') { take(); void copy(selected, true); return }
    if (mod && selected.length && k === 'd') { take(); void duplicate(selected); return }
    if (mod && selected.length && (e.key === ']' || e.key === '[')) { take(); void restack(selected, e.key === ']'); return }
    if (e.key === ' ') { take(); setSpace(true); return }
    if (!mod && !e.altKey) {
      const picked = TOOLS.find((id) => TOOL_KEYS[id] === k)
      if (picked) { take(); setTool(picked); return }
    }
    // Esc in the middle of a drag drops nothing: the items go back where they were.
    if (e.key === 'Escape' && drag) { take(); setDrag(null); setGuides([]); setSelection([]); return }
    if (e.key === 'Escape' && tool !== 'select') { take(); setTool('select'); return }
    if (!selected.length) return
    if (e.key === 'Escape') { take(); setSelection([]); return }
    // Tab steps through the plan's items while something is selected; Esc lets Tab leave the plan again.
    if (e.key === 'Tab' && !mod && !e.altKey) {
      const next = nextItem(data, selected[selected.length - 1], e.shiftKey)
      if (next) { take(); pick([next]); follow(next) }
      return
    }
    if (mod && e.shiftKey && k === 'l') { take(); void setLocked(selected, !allLocked); return }
    if (e.key === 'Delete' || e.key === 'Backspace') { take(); void remove(selected); return }
    if (k === 'r' && !mod && !e.altKey) { take(); void rotate(selected, e.shiftKey); return }
    if (k === 'f' && !mod && !e.altKey) { take(); frame(selected); return }
    const dirs: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
    const dir = dirs[e.key]
    if (dir) {
      take()
      const n = NUDGE_PCT * (e.shiftKey ? 5 : 1)
      const d = fromPct(data.size, { x: dir[0] * n, y: dir[1] * n })
      void moveBy(selected, d)
    }
  }
  const onKeyUp = (e: React.KeyboardEvent) => { if (e.key === ' ') setSpace(false) }
  // A dialog that closed hands the keys back to the plan, so Ctrl+Z undoes what it just did.
  const dialogOpen = !!placing || !!cableForm || !!filling
  const wasOpen = useRef(false)
  useEffect(() => {
    if (wasOpen.current && !dialogOpen) document.querySelector<SVGSVGElement>('.fb-plan-editor svg.fb-plan')?.focus()
    wasOpen.current = dialogOpen
  }, [dialogOpen])
  useEffect(() => {
    const off = () => setSpace(false)
    window.addEventListener('blur', off)
    return () => window.removeEventListener('blur', off)
  }, [])

  /** Where a drag puts the selection: on another item's edge or middle when one is within six
   *  pixels (the guide shows), otherwise on the grid; Alt places freely. */
  const dragTo = (raw: Point, snap: boolean, lead: ItemRef, px: number): { d: Point; guides: Guide[] } => {
    const grid = snappedDelta(data, lead, raw, snap && snapping.grid)
    if (!snap || !snapping.items) return { d: grid, guides: [] }
    const g = snapToGuides(data, selected, raw, 6 * px, present.filter((r) => r.kind !== 'cable'))
    const on = (axis: 'x' | 'y') => g.guides.some((x) => x.axis === axis)
    return { d: { x: on('x') ? g.d.x : grid.x, y: on('y') ? g.d.y : grid.y }, guides: g.guides }
  }
  // ``alone``: Ctrl-click took one item out of its group's selection, so only it moves.
  const pick = (next: ItemRef[], alone = false) => setSelection(alone ? next : withGroups(next, groups))
  /** Moves the view so ``ref`` is on screen (keyboard users can't see what they picked otherwise). */
  /** F: the view closes in on the selection. */
  const frame = (refs: ItemRef[]) => { const v = frameOf(data, refs, view); if (v) setView(v) }
  const follow = (ref: ItemRef) => {
    const c = outlineOf(data, ref)?.centre
    if (!c) return
    const m = Math.min(view.w, view.h) * 0.1
    if (c.x < view.x + m || c.x > view.x + view.w - m || c.y < view.y + m || c.y > view.y + view.h - m) {
      setView({ ...view, x: c.x - view.w / 2, y: c.y - view.h / 2 })
    }
  }
  const grouped = groupsOf(groups, selected).length > 0
  const movable = selected.filter((r) => r.kind !== 'cable')
  // Inventory switches only leave the plan (they stay in the inventory): say so on the button.
  const onlyUnplace = selected.length > 0 && selected.every((r) => r.kind === 'switch' && !data.switches.find((w) => w.id === r.id)?.manual)
  // Group again only when that changes something: not one whole group already.
  const canTurn = quarterTurns(data, unlocked(selected)).length > 0
  // Lock while any of it is free to move; unlock once all of it is locked.
  const allLocked = movable.length > 0 && movable.every(isLocked)
  const lockedSel = movable.filter(isLocked)
  const canGroup = movable.length > 1 && !(groupsOf(groups, movable).length === 1 && groupsOf(groups, movable)[0].members.every((m) => movable.some((r) => sameRef(r, m))))

  const one = selected.length === 1 ? selected[0] : null
  const oneCable = one?.kind === 'cable' ? cables.find((c) => c.ref.cable === one.id) ?? null : null
  const arrangedShape = one?.kind === 'block' && arranging === one.id && !isLocked(one) ? data.drawing?.shapes.find((s) => s.id === one.id) ?? null : null
  // The bars between rows: a block in rows (not seats placed by hand), not locked, not being arranged.
  const gapShape = one?.kind === 'block' && arranging !== one.id && !isLocked(one) ? data.drawing?.shapes.find((s) => s.id === one.id && !s.free) ?? null : null
  const gapRows = gapShape ? storedBlocks.data?.find((b) => b.id === gapShape.id && !b.seat_at)?.rows ?? null : null
  // The picked row, when it has a shape to change on the plan (RowShapeHandles.tsx).
  // The Rows tab always has a row open (the first until another is picked), so the plan shows its handles too.
  // Where the Rows tab's split button cuts the block: above the picked row (#1208).
  const splitAt = useMemo(() => {
    const stored = oneBlock ? storedBlocks.data?.find((b) => b.id === oneBlock) : undefined
    const id = pickedRow?.block === oneBlock ? pickedRow.row : null
    const index = stored && id ? stored.rows.findIndex((r) => r.id === id) : -1
    if (!stored || index <= 0 || isLocked({ kind: 'block', id: stored.id })) return null
    const names = (stored as { row_names?: string[] }).row_names ?? []
    return { index, name: names[index] ?? String(index + 1), freely: !!stored.seat_at && Object.keys(stored.seat_at as object).length > 0 }
  }, [oneBlock, storedBlocks.data, pickedRow, isLocked])
  const rowPicked = gapShape && gapRows ? (pickedRow?.block === gapShape.id ? pickedRow!.row : tab === 'rows' ? gapRows[0]?.id ?? null : null) : null
  const shapedRow = gapRows && rowPicked ? gapRows.findIndex((r) => r.id === rowPicked && r.shape !== 'line') : -1
  // The picked row of any shape, for its letter (RowLabelHandle.tsx).
  const labelRow = gapRows && rowPicked ? gapRows.findIndex((r) => r.id === rowPicked) : -1
  const oneMark = one?.kind === 'mark' ? shown.drawing?.marks?.find((m) => m.id === one.id) ?? null : null
  const markBox = oneMark && one ? outlineOf(shown, one)?.box : null
  // From the saved plan: the handle turns round where the item is, not where a drag drew it.
  const turnable = one && !isLocked(one) && canTurnOne(data, one) ? outlineOf(data, one) : null
  // From the saved plan, not the one drawn while dragging: the handles start over once a change is
  // saved (a wall's new bend is a new handle), but not mid-drag, which would drop the pointer.
  const handlesKey = (id: string) => { const m = data.drawing?.marks?.find((x) => x.id === id); return m ? `${id}:${JSON.stringify([m.x, m.y, m.x2, m.y2, m.points])}` : id }
  const reshaped = (m: PlanMark) => {
    const was = data.drawing?.marks?.find((x) => x.id === m.id)
    setShaping({ mark: m, data, done: true })
    if (was) void change({ kind: 'mark', id: m.id! }, shapeBody(was, data.size), shapeBody(m, data.size))
  }
  const routeOf = (c: PlanCable): Route => c.points.map(([x, y]) => fromPct(data.size, { x, y }))
  const pathOf = (r: Route) => cablePath(r.map((p) => { const v = toPct(data.size, p); return [v.x, v.y] as [number, number] }), data.size, oneCable?.corners)
  // One board with seat blocks or switches: the panel offers to feed them from one of its circuits.
  const boards = selected.filter((r) => r.kind === 'board')
  const boardSel = boards.length === 1 ? boards[0].id : null
  const feedable = selected.filter((r) => r.kind === 'block' || r.kind === 'switch')
  // A drag redraws the editor on every pointer move; the panel shows nothing that changes until
  // the drop, so it (and the closed dialogs) shows the copy taken when the drag starts instead of being drawn again (Mike: moving
  // a row dragged behind a lot).
  // While dragging, the rulers mark the middle of what moves rather than the pointer.
  const dragMid = useMemo(() => {
    if (!drag) return null
    const boxes = unlocked(selected).map((r) => outlineOf(shown, r)?.box).filter((b) => !!b)
    if (!boxes.length) return null
    const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y))
    const x1 = Math.max(...boxes.map((b) => b.x + b.w)), y1 = Math.max(...boxes.map((b) => b.y + b.h))
    return { x: (x0 + x1) / 2, y: (y0 + y1) / 2 }
  }, [drag, selected, shown, unlocked])
  const tabNow: PanelTab = (tab === 'rows' || tab === 'seats') && !oneBlock ? 'edit' : tab
  const rowCount = oneBlock ? data.drawing?.shapes.find((b) => b.id === oneBlock)?.row_list?.length ?? 0 : 0
  const rail = useMemo(() => <ToolRail tool={tool} onTool={setTool} onView={onDone} />, [tool, onDone])
  const panel = (<>
    <FillAreaDialog box={filling} hall={data.hall} onClose={() => setFilling(null)} onFill={fillArea} />
    <PlaceBlockDialog opened={placing?.kind === 'block'} onClose={() => setPlacing(null)} onCreate={placeBlock} />
    <PlaceMarkDialog kind={placing && (placing.kind === 'text' || placing.kind === 'icon') ? placing.kind : null} onClose={() => setPlacing(null)} onCreate={placeMark} />
    <PlacePanelDialog opened={placing?.kind === 'panel'} names={(data.panels ?? []).map((p) => p.name)} onClose={() => setPlacing(null)} onCreate={placePanel} />
    <PlanDialogs open={dialog} data={data} onClose={() => onDialog(null)} onHall={onHall} onChanged={refresh}
      onReplaced={() => { history.clear(); return refresh() }} onPlace={(p) => void placePreset(p)} />
    <SavePresetDialog items={presetDraft} onClose={() => setPresetDraft(null)} />
    <PlaceSwitchDialog opened={placing?.kind === 'switch'} onClose={() => setPlacing(null)} onPlace={placeSwitches} />
    <PlaceBoardDialog opened={placing?.kind === 'board'} names={(markers.data?.boards ?? []).map((b) => b.name)} onClose={() => setPlacing(null)} onCreate={placeBoard} />
    {cableForm && <CableModal key={cableForm.cable?.id ?? 'new'} cable={cableForm.cable} canEdit initial={cableForm.initial}
      onClose={() => setCableForm(null)} onDone={(c) => void cableDone(c)} />}
    <div className="fb-edit-side">
    <PanelResize width={panelWidth} onWidth={setPanelWidth} />
    {under && (
      <UnstyledButton className="fb-edit-grab" aria-expanded={!folded} aria-label={t(folded ? 'planSheet.show' : 'planSheet.hide')}
        onClick={() => setFoldedAt(folded ? null : selKey)}><span aria-hidden="true" /></UnstyledButton>
    )}
    <Paper withBorder radius="lg" p="md" className="fb-edit-panel">
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600}>{one ? itemTitle(t, data, one) : selected.length ? t('plan.edit.selected', { count: selected.length }) : t('plan.edit.title')}</Text>
          <Group gap={4} wrap="nowrap">
            <Tooltip label={history.nextUndo ? t('plan.edit.undoWhat', { what: history.nextUndo }) : t('plan.edit.undo')}>
              <ActionIcon variant="default" aria-label={t('plan.edit.undo')} disabled={!history.canUndo} onClick={() => void step('undo')}><IconArrowBackUp size={16} /></ActionIcon>
            </Tooltip>
            <Tooltip label={history.nextRedo ? t('plan.edit.redoWhat', { what: history.nextRedo }) : t('plan.edit.redo')}>
              <ActionIcon variant="default" aria-label={t('plan.edit.redo')} disabled={!history.canRedo} onClick={() => void step('redo')}><IconArrowForwardUp size={16} /></ActionIcon>
            </Tooltip>
            <Menu position="bottom-end" withinPortal shadow="md" width={260}>
              <Menu.Target>
                <Tooltip label={t('plan.edit.history.title')}>
                  <ActionIcon variant="default" aria-label={t('plan.edit.history.title')} disabled={!history.canUndo && !history.canRedo}><IconHistory size={16} /></ActionIcon>
                </Tooltip>
              </Menu.Target>
              <Menu.Dropdown mah={360} style={{ overflowY: 'auto' }}>
                <Text size="xs" c="dimmed" px="sm" py={6}>{t('plan.edit.history.help')}</Text>
                {history.future.map((label, i) => (
                  <Menu.Item key={`f${i}`} c="dimmed" onClick={() => void jump('redo', history.future.length - i)}>{upFirst(label)}</Menu.Item>
                ))}
                {history.past.map((label, i) => (
                  <Menu.Item key={`p${i}`} fw={i === 0 ? 600 : undefined} rightSection={i === 0 ? <Text size="xs" c="dimmed">{t('plan.edit.history.latest')}</Text> : undefined}
                    onClick={() => void jump('undo', i + 1)}>{upFirst(label)}</Menu.Item>
                ))}
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
        {!folded && <>
        <Tabs value={tabNow} onChange={(v) => v && setTab(v as PanelTab)} keepMounted={false} className="fb-edit-tabs">
          <Tabs.List grow>
            <Tabs.Tab value="edit">{t(oneBlock ? 'editPanel.block' : selected.length ? 'editPanel.selection' : 'editPanel.plan')}</Tabs.Tab>
            {oneBlock && <Tabs.Tab value="rows" rightSection={rowCount ? <Badge size="xs" variant="light" color="gray" circle>{rowCount}</Badge> : null}>{t('editPanel.rows')}</Tabs.Tab>}
            {oneBlock && <Tabs.Tab value="seats">{t('editPanel.seats')}</Tabs.Tab>}
            <Tabs.Tab value="items">{t('editPanel.items')}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="edit" pt="md">
            <Stack gap="sm">
                {one && <ItemFields key={refKey(one)} section={oneBlock ? 'block' : undefined} data={data} item={one} onChange={change} arranging={arranging === one.id} onArrange={(on) => setArranging(on ? one.id : null)}
                  picked={pickedRow?.block === one.id ? pickedRow.row : null} onPick={(id) => setPickedRow(id ? { block: one.id, row: id } : null)} />}
                {one?.kind === 'switch' && (
                  <Text size="sm" c="dimmed">{t(data.switches.find((w) => w.id === one.id)?.manual ? 'plan.edit.switch.manualNote' : 'plan.edit.switch.inventoryNote')}</Text>
                )}
                {one?.kind === 'panel' && data.panels?.find((p) => p.name === one.id) && (
                  <PanelFields key={`p-${one.id}`} panel={data.panels.find((p) => p.name === one.id)!} onPorts={(a, b) => change(one, { ports: a }, { ports: b })} />
                )}
                {one && oneCable && (
                  <CableFields cable={oneCable} onEdit={() => void editCable(one.id)}
                    onCorners={(corners) => void setRoute(oneCable, { points: oneCable.manual ? bendsOf(oneCable) : null, corners }, t('plan.edit.step.corners'))}
                    onReset={() => void setRoute(oneCable, { points: null, corners: 'square' }, t('plan.edit.step.autoRoute'))}
                    onEnds={(change) => void changeEnds(one.id, change)} />
                )}
                {boardSel && (
                  <BoardFields key={`b-${boardSel}`} board={boardSel} feedable={feedable.length}
                    onAddCircuit={(name) => addCircuit(boardSel, name)} onFeed={(c) => feed(c, feedable)} />
                )}
                {selected.length > 1 && <SharedFields fields={sharedFields(data, selected)} onChange={(f, v) => void changeAll(selected, f, v)} />}
                {lockedSel.length > 0 && <Text size="xs" c="dimmed">{t('plan.edit.lockedN', { count: lockedSel.length })}</Text>}
                {movable.length > 1 && (
                  <Arrange count={movable.length} grouped={grouped} canGroup={canGroup}
                    onAlign={(how) => void moveEach(alignMoves(data, movable, how), t('plan.edit.step.align'))}
                    onDistribute={(axis) => void moveEach(distributeMoves(data, movable, axis), t('plan.edit.step.distribute'))}
                    onGroup={(join) => void regroup(selected, join)} />
                )}
                {selected.length > 1 && selected.every((r) => r.kind === 'block') && (
                  <MergeBlocks count={selected.length} disabled={lockedSel.length > 0} onMerge={() => void join.merge(selected.map((r) => r.id))} />
                )}
                {selected.length > 0 && (
                  <QuickActions canTurn={canTurn} locked={movable.length ? allLocked : null} onLock={() => void setLocked(selected, !allLocked)} onDuplicate={() => void duplicate(selected)} onRotate={() => void rotate(selected, false)}
                    onFront={() => void restack(selected, true)} onBack={() => void restack(selected, false)} onFrame={() => frame(selected)} />
                )}
                {selected.length > 0 && (
                  <Button variant="light" color="down" leftSection={<IconTrash size={16} />} disabled={allLocked} onClick={() => void remove(selected)}>
                    {t(onlyUnplace ? 'plan.edit.unplace' : 'plan.edit.delete', { count: selected.length })}
                  </Button>
                )}
                {!selected.length && tool === 'select' && data.background && (
                  <BackgroundFields opacity={data.background_opacity ?? 1} placing={bgPlacing} seatM={data.seat_m} onPlacing={setBgPlacing}
                    onOpacity={(v) => void changeHall('background', { opacity: data.background_opacity ?? 1 }, { opacity: v }, t('plan.edit.step.background'))}
                    onFit={() => placeBackground(null)} />
                )}
                {tool === 'measure' && measured && (() => {
                  const seats = Math.hypot(measured.b.x - measured.a.x, measured.b.y - measured.a.y) / (data.drawing?.cell ?? 32)
                  return (
                    <CalibrateFields seats={seats} seatM={data.seat_m} hasBackground={!!data.background}
                      onScale={(m) => void changeHall('scale', { seat_m: data.seat_m ?? null }, { seat_m: seatMetres(seats, m) }, t('plan.edit.step.scale'))}
                      onFit={(m) => placeBackground(scaleFrame(bgFrame, measured.a, fitFactor(seats, m, data.seat_m!)))} />
                  )
                })()}
                {!selected.length && (
                  <Text size="sm" c="dimmed">{t(tool === 'select' ? 'plan.edit.help' : `plan.edit.hint.${tool}`)}</Text>
                )}
                {!selected.length && hallIsEmpty(data) && <EmptyHall onStart={() => onDialog('start')} />}
                {small && !selected.length && <Text size="xs" c="dimmed">{t('plan.edit.smallScreen')}</Text>}
            </Stack>
          </Tabs.Panel>
          {oneBlock && (
            <Tabs.Panel value="rows" pt="md">
              <Stack gap="sm">
                <ItemFields key={`${refKey(one!)}-rows`} section="rows" data={data} item={one!} onChange={change} arranging={arranging === one!.id} onArrange={(on) => setArranging(on ? one!.id : null)}
              picked={pickedRow?.block === one!.id ? pickedRow.row : null} onPick={(id) => setPickedRow(id ? { block: one!.id, row: id } : null)} />
                {splitAt && (
                  <SplitBlock index={splitAt.index} name={splitAt.name} freely={splitAt.freely}
                    onSplit={() => void join.split(oneBlock, splitAt.index)} />
                )}
              </Stack>
            </Tabs.Panel>
          )}
          {oneBlock && (
            <Tabs.Panel value="seats" pt="md">
              <Stack gap="sm">
                <ItemFields key={`${refKey(one!)}-seats`} section="seats" data={data} item={one!} onChange={change} arranging={arranging === one!.id} onArrange={(on) => setArranging(on ? one!.id : null)}
              picked={pickedRow?.block === one!.id ? pickedRow.row : null} onPick={(id) => setPickedRow(id ? { block: one!.id, row: id } : null)} />
              </Stack>
            </Tabs.Panel>
          )}
          <Tabs.Panel value="items" pt="md">
                <ItemList data={data} groups={groups} selected={selected}
                  onSelect={(refs, add) => pick(add ? [...selected, ...refs.filter((r) => !selected.some((x) => sameRef(x, r)))] : refs)}
                  onRename={(g, name) => void renameGroup(g, name)}
                  onUngroup={(g) => void regroup(g.members, false)} onFrame={frame} />
          </Tabs.Panel>
        </Tabs>
        <Text size="xs" c="dimmed">
          <Kbd size="xs">Del</Kbd> {t('plan.edit.keys.delete')} · <Kbd size="xs">←↑↓→</Kbd> {t('plan.edit.keys.nudge')} · <Kbd size="xs">Alt</Kbd> {t('plan.edit.keys.free')} · <Kbd size="xs">Space</Kbd> {t('plan.edit.keys.pan')}
        </Text>
        <Text size="xs" c="dimmed">
          {t('plan.edit.keys.more')}{' · '}
          <Anchor component="button" type="button" size="xs" onClick={onShortcuts}>{t('plan.shortcuts.allKeys')}</Anchor> <Kbd size="xs">?</Kbd>
        </Text>
        <Attribution compact />
        </>}
      </Stack>
    </Paper>
    </div>
  </>)
  return (
    <div className={`fb-plan-layout with-inspector fb-plan-editor${folded ? ' is-folded' : ''}`} onKeyDownCapture={onKey} onKeyUpCapture={onKeyUp}
      style={panelWidth ? ({ '--fb-edit-w': `${panelWidth}px` } as React.CSSProperties) : undefined}>
      <div className="fb-edit-stage">
      {rail}
      <SeatMap data={shown} view={view} setView={setView} filter={filter} selected={null} layers={layers} onSelect={() => {}} cables={cablePlan?.cables} power={power} {...live}
        overlay={(ctx) => (<>
          <EditOverlay ctx={ctx} data={shown} selection={selected} onSelect={pick} together={(r) => withGroups([r], groups)} space={space} tool={tool} snapping={snapping}
            lines={followPlan(cables, shown).map((c) => ({ ref: { kind: 'cable', id: c.ref.cable! }, d: cablePath(c.points, data.size, c.corners) }))}
            onPlace={(at, raw) => {
              if (tool === 'block' || tool === 'switch' || tool === 'text' || tool === 'icon' || tool === 'panel' || tool === 'board') setPlacing({ kind: tool, at })
              else if (tool === 'cable') startCable(raw)
            }}
            onLine={drawLine} onBox={(b) => { if (tool === 'fill') { const size = toPct(data.size, { x: b.w, y: b.h }); setFilling({ ...pct(b), w: size.x, h: size.y }) } else void drawZone(b) }} onMeasure={setMeasured}
            onPointer={(p) => { pointer.current = pct(p) }}
            onMenu={(item, x, y) => setMenu({ item, x, y, at: pointer.current })}
            onDouble={pickRowAt}
            guides={guides}
            onDrag={(raw, snap, lead, px) => { if (!drag) setFrozenPanel(panel); const g = dragTo(raw, snap, lead, px); setGuides(g.guides); setDrag({ d: g.d }) }}
            onDrop={(raw, snap, lead, px) => { setDrag(null); setFrozenPanel(null); setGuides([]); void moveBy(selected, dragTo(raw, snap, lead, px).d) }} />
          {bgPlacing && data.background && tool === 'select' && (
            <BackgroundHandles ctx={ctx} frame={bgFrame} onDraft={(f) => setBgDraft(f ? { frame: f, data } : null)} onDone={placeBackground} />
          )}
          {snapping.rulers && <Rulers ctx={ctx} cell={data.drawing?.cell ?? 32} at={dragMid} />}
          {lockedSel.length > 0 && tool === 'select' && <LockBadges ctx={ctx} boxes={lockedSel.map((r) => outlineOf(shown, r)).filter((o) => !!o)} />}
          {oneMark && markBox && tool === 'select' && !drag && !isLocked(one!) && (
            <MarkHandles key={handlesKey(oneMark.id!)} ctx={ctx} mark={oneMark}
              corner={{ x: markBox.x + markBox.w, y: markBox.y + markBox.h }} size={data.size} cell={data.drawing?.cell ?? 32}
              anchors={isLine(oneMark) && snapping.items ? wallCorners(data, oneMark.id) : undefined} snapGrid={snapping.grid} seatM={data.seat_m}
              onDraft={(m) => setShaping(m ? { mark: m, data } : null)} onDone={reshaped} />
          )}
          {one && turnable && tool === 'select' && !drag && (
            <RotateHandle key={refKey(one)} ctx={ctx} box={turnable.box} centre={turnable.centre} rotation={turnable.rotation}
              onDraft={(deg) => setTurning(deg == null ? null : { ref: one, deg, data })}
              onDone={(deg) => {
                setTurning({ ref: one, deg, data, done: true })
                void change(one, { rotation: turnable.rotation }, { rotation: deg })
              }} />
          )}
          {arrangedShape && tool === 'select' && !drag && (
            <SeatHandles ctx={ctx} shape={arrangedShape} cell={data.drawing?.cell ?? 32} snapGrid={snapping.grid}
              onDone={(moves) => {
                const cell = data.drawing?.cell ?? 32
                void change(one!, placedNow(arrangedShape, cell, data.size), moveSeats(arrangedShape, cell, data.size, moves))
              }} />
          )}
          {gapShape && gapRows && tool === 'select' && !drag && (
            <RowGapHandles key={JSON.stringify(gapRows.map((r) => r.gap))} ctx={ctx} shape={gapShape} cell={data.drawing?.cell ?? 32}
              gaps={gapRows.map((r) => r.gap)} snapGrid={snapping.grid}
              picked={rowPicked ? gapRows.findIndex((r) => r.id === rowPicked) : null}
              onPick={(i) => setPickedRow({ block: one!.id, row: gapRows[i].id })}
              onDone={(i, gap) => void moveGap(one!, gapShape, gapRows, i, gap)} />
          )}
          {/* Under the shape handles, so a path point beside the letter can still be grabbed. */}
          {gapShape && gapRows && labelRow >= 0 && tool === 'select' && !drag && (
            <RowLabelHandle key={JSON.stringify([gapRows[labelRow], gapShape.rows])} ctx={ctx} shape={gapShape} cell={data.drawing?.cell ?? 32}
              row={gapRows[labelRow]} r={labelRow} snapGrid={snapping.grid}
              onDone={(row) => void reshapeRow(one!, gapShape, gapRows, labelRow, row, keepTop(gapShape, data.drawing?.cell ?? 32, data.size, 0))} />
          )}
          {gapShape && gapRows && shapedRow >= 0 && tool === 'select' && !drag && (
            <RowShapeHandles key={JSON.stringify(gapRows[shapedRow])} ctx={ctx} shape={gapShape} cell={data.drawing?.cell ?? 32} size={data.size}
              rows={gapRows} r={shapedRow} snapGrid={snapping.grid} onDone={(row, place) => void reshapeRow(one!, gapShape, gapRows, shapedRow, row, place)} />
          )}
          {oneCable && tool === 'select' && (
            <BendHandles key={JSON.stringify(oneCable.points)} ctx={ctx} route={routeOf(oneCable)} cell={data.drawing?.cell ?? 32} path={pathOf}
              onChange={(r) => void setRoute(oneCable, { points: bendsPct(r, data.size), corners: oneCable.corners === 'straight' ? 'square' : oneCable.corners }, t('plan.edit.step.bend'))} />
          )}
        </>)} />
      </div>
      {menu && (
        <Menu opened onChange={(o) => { if (!o) setMenu(null) }} position="bottom-start" offset={2} withinPortal shadow="md" width={220}>
          <Menu.Target><div style={{ position: 'fixed', left: menu.x, top: menu.y, width: 1, height: 1 }} /></Menu.Target>
          <Menu.Dropdown>
            {menu.item && (
              <>
                <Menu.Label>{selected.length > 1 ? t('plan.edit.selected', { count: selected.length }) : itemTitle(t, data, menu.item)}</Menu.Label>
                <Menu.Item leftSection={<IconCopy size={14} />} rightSection={<Kbd size="xs">Ctrl D</Kbd>} onClick={() => void duplicate(selected)}>{t('plan.edit.menu.duplicate')}</Menu.Item>
                <Menu.Item leftSection={<IconCopy size={14} />} rightSection={<Kbd size="xs">Ctrl C</Kbd>} onClick={() => void copy(selected)}>{t('plan.edit.menu.copy')}</Menu.Item>
                <Menu.Item leftSection={<IconCut size={14} />} rightSection={<Kbd size="xs">Ctrl X</Kbd>} onClick={() => void copy(selected, true)}>{t('plan.edit.menu.cut')}</Menu.Item>
                <Menu.Item leftSection={<IconBookmark size={14} />} onClick={() => void saveAsPreset(selected)}>{t('presets.menuSave')}</Menu.Item>
              </>
            )}
            <Menu.Item leftSection={<IconClipboard size={14} />} rightSection={<Kbd size="xs">Ctrl V</Kbd>} disabled={!readClip()?.length}
              onClick={() => void paste(menu.at ?? undefined)}>{t('plan.edit.menu.paste')}</Menu.Item>
            {!menu.item && (
              <Menu.Item leftSection={<IconBookmarks size={14} />} onClick={() => { presetAt.current = menu.at; onDialog('presets') }}>{t('presets.menuPlace')}</Menu.Item>
            )}
            {menu.item && (
              <>
                {(canGroup || grouped) && <Menu.Divider />}
                {canGroup && (
                  <Menu.Item leftSection={<IconLink size={14} />} rightSection={<Kbd size="xs">Ctrl G</Kbd>} onClick={() => void regroup(selected, true)}>{t('plan.edit.menu.group')}</Menu.Item>
                )}
                {grouped && (
                  <Menu.Item leftSection={<IconUnlink size={14} />} rightSection={<Kbd size="xs">Ctrl ⇧ G</Kbd>} onClick={() => void regroup(selected, false)}>{t('plan.edit.menu.ungroup')}</Menu.Item>
                )}
                <Menu.Divider />
                <Menu.Item leftSection={<IconStack2 size={14} />} rightSection={<Kbd size="xs">Ctrl ]</Kbd>} onClick={() => void restack(selected, true)}>{t('plan.edit.menu.front')}</Menu.Item>
                <Menu.Item leftSection={<IconLayersSubtract size={14} />} rightSection={<Kbd size="xs">Ctrl [</Kbd>} onClick={() => void restack(selected, false)}>{t('plan.edit.menu.back')}</Menu.Item>
                <Menu.Item leftSection={<IconZoomIn size={14} />} rightSection={<Kbd size="xs">F</Kbd>} onClick={() => frame(selected)}>{t('plan.edit.menu.frame')}</Menu.Item>
                <Menu.Item leftSection={<IconSelectAll size={14} />} rightSection={<Kbd size="xs">Ctrl ⇧ A</Kbd>} onClick={() => setSelection(similar(data, present, selected))}>{t('plan.edit.menu.similar')}</Menu.Item>
                {canTurn && (
                  <Menu.Item leftSection={<IconRotateClockwise size={14} />} rightSection={<Kbd size="xs">R</Kbd>} onClick={() => void rotate(selected, false)}>{t('plan.edit.menu.rotate')}</Menu.Item>
                )}
                {movable.length > 0 && (
                  <Menu.Item leftSection={allLocked ? <IconLockOpen size={14} /> : <IconLock size={14} />} rightSection={<Kbd size="xs">Ctrl ⇧ L</Kbd>}
                    onClick={() => void setLocked(selected, !allLocked)}>{t(allLocked ? 'plan.edit.menu.unlock' : 'plan.edit.menu.lock')}</Menu.Item>
                )}
                {selected.length > 0 && (
                  <>
                    <Menu.Divider />
                    <Menu.Item color="down" leftSection={<IconTrash size={14} />} rightSection={<Kbd size="xs">Del</Kbd>} onClick={() => void remove(selected)}>{t(onlyUnplace ? 'plan.edit.menu.unplace' : 'plan.edit.menu.delete')}</Menu.Item>
                  </>
                )}
              </>
            )}
          </Menu.Dropdown>
        </Menu>
      )}
      <VisuallyHidden role="status" aria-live="polite">
        {one ? itemTitle(t, data, one) : selected.length ? t('plan.edit.selected', { count: selected.length }) : ''}
      </VisuallyHidden>
      {drag && frozenPanel ? frozenPanel : panel}
    </div>
  )
}

function itemTitle(t: (k: string, o?: Record<string, unknown>) => string, data: SeatViewData, ref: ItemRef) {
  if (ref.kind === 'block') return t('plan.edit.kind.block', { name: blockName(data.drawing?.shapes.find((s) => s.id === ref.id)) })
  if (ref.kind === 'switch') return t('plan.edit.kind.switch', { name: data.switches.find((w) => w.id === ref.id)?.name ?? '' })
  if (ref.kind === 'panel') return t('plan.edit.kind.panel', { name: ref.id })
  if (ref.kind === 'cable') return t('plan.edit.kind.cable')
  if (ref.kind === 'board') return t('plan.edit.kind.board', { name: data.boards?.find((b) => b.id === ref.id)?.name ?? '' })
  const m = data.drawing?.marks?.find((x) => x.id === ref.id)
  return t(`plan.edit.kind.${m?.kind ?? 'text'}`)
}


/** One item's fields. Each change is saved on its own (Enter or leaving a text field). */
type PanelTab = 'edit' | 'rows' | 'seats' | 'items'

function ItemFields({ data, item, onChange, arranging, onArrange, picked, onPick, section }: {
  data: SeatViewData; item: ItemRef
  section?: 'block' | 'rows' | 'seats'
  onChange: (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>
  arranging?: boolean
  onArrange?: (on: boolean) => void
  picked?: string | null
  onPick?: (id: string | null) => void
}) {
  const { t } = useTranslation()
  const shape = item.kind === 'block' ? data.drawing?.shapes.find((s) => s.id === item.id) : undefined
  const mark = item.kind === 'mark' ? data.drawing?.marks?.find((m) => m.id === item.id) : undefined
  const [name, setName] = useState(shape?.name ?? mark?.text ?? mark?.label ?? '')
  const set = (field: string, before: unknown, after: unknown) => { if (before !== after) void onChange(item, { [field]: before }, { [field]: after }) }
  const turn = (value: number, field = 'rotation') => (
    <div>
      <Text size="sm" fw={500} mb={4}>{t('plan.edit.rotation')}</Text>
      <Group gap="xs" wrap="nowrap">
        {/* A free angle (from the rotate handle) leaves the quarter steps unpicked. */}
        <SegmentedControl style={{ flex: 1 }} value={String(value)} data={['0', '90', '180', '270'].map((v) => ({ value: v, label: `${v}°` }))}
          onChange={(v) => set(field, value, Number(v))} />
        <NumberInput key={value} w={84} min={0} max={359} step={1} suffix="°" defaultValue={value} aria-label={t('plan.edit.rotationDegrees')} clampBehavior="strict"
          onBlur={(e) => { const v = Number(e.currentTarget.value.replace('°', '')); if (Number.isFinite(v)) set(field, value, ((Math.round(v) % 360) + 360) % 360) }}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
      </Group>
    </div>
  )
  if (shape) {
    if (section && section !== 'block') {
      return <BlockFields item={item} data={data} onChange={onChange} arranging={arranging} onArrange={onArrange} picked={picked} onPick={onPick} section={section} />
    }
    return (
      <>
        <TextInput label={t('plan.edit.name')} value={name} maxLength={40} onChange={(e) => setName(e.currentTarget.value)} onBlur={() => set('name', shape.name, name)}
          onKeyDown={(e) => { if (e.key === 'Enter') set('name', shape.name, name) }} />
        {turn(shape.rotation)}
        <BlockFields item={item} data={data} onChange={onChange} arranging={arranging} onArrange={onArrange} picked={picked} onPick={onPick} section={section} />
      </>
    )
  }
  if (!mark) return null
  const layer = (
    <Select label={t('plan.edit.layer')} allowDeselect={false} value={mark.layer ?? 'overview'} onChange={(v) => v && set('layer', mark.layer ?? 'overview', v)}
      data={LAYER_IDS.map((l) => ({ value: l, label: t(`plan.edit.layers.${l}`) }))} />
  )
  const tint = <TintField key={mark.tint ?? ''} value={mark.tint ?? null} onChange={(v) => set('tint', mark.tint ?? null, v)} />
  const size = (
    <div>
      <Text size="sm" fw={500} mb={4}>{t('plan.edit.mark.size')}</Text>
      {/* Picking a size step also drops a stretch from the corner handle. */}
      <SegmentedControl fullWidth value={mark.size ?? 'm'}
        onChange={(v) => void onChange(item, { size: mark.size ?? 'm', scale: mark.scale ?? 1 }, { size: v, scale: 1 })}
        data={['s', 'm', 'l'].map((x) => ({ value: x, label: t(`plan.edit.mark.sizes.${x}`) }))} />
      <Text size="xs" c="dimmed" mt={4}>
        {(mark.scale ?? 1) !== 1 ? t('plan.edit.mark.scaled', { pct: Math.round((mark.scale ?? 1) * 100) }) : t('plan.edit.mark.scaleHelp')}
      </Text>
    </div>
  )
  if (mark.kind === 'text' || mark.kind === 'zone') {
    const field = mark.kind === 'text' ? 'text' : 'label'
    const before = (mark.kind === 'text' ? mark.text : mark.label) ?? ''
    return (
      <>
        <TextInput label={t(mark.kind === 'text' ? 'plan.edit.text' : 'plan.edit.label')} value={name} onChange={(e) => setName(e.currentTarget.value)}
          onBlur={() => set(field, before, name)} onKeyDown={(e) => { if (e.key === 'Enter') set(field, before, name) }} />
        {mark.kind === 'text' && <>{size}{turn(mark.rotation ?? 0)}</>}
        {mark.kind === 'zone' && turn(mark.rotation ?? 0)}
        {mark.kind === 'zone' && (
          <div>
            <Text size="sm" fw={500} mb={4}>{t('plan.edit.color')}</Text>
            <Group gap="xs">
              {ZONE_COLORS.map((c) => (
                <Tooltip key={c} label={t(`plan.edit.colors.${c}`)}>
                  <ColorSwatch component="button" type="button" color={`var(--color-${c === 'muted' ? 'muted' : c})`} size={26}
                    aria-label={t(`plan.edit.colors.${c}`)} aria-pressed={(mark.color ?? 'muted') === c} onClick={() => set('color', mark.color ?? 'muted', c)}
                    style={{ outline: (mark.color ?? 'muted') === c ? '2px solid var(--bnb-fg)' : undefined, outlineOffset: 2 }} />
                </Tooltip>
              ))}
            </Group>
          </div>
        )}
        {tint}
        {layer}
      </>
    )
  }
  if (mark.kind === 'walkway') {
    return (
      <>
        <WalkwayFields mark={mark} onWidth={(before, after) => set('width', before, after)}
          onStraighten={() => void onChange(item, { points: shapeBody(mark, data.size).points }, { points: [] })} />
        {tint}
        {layer}
      </>
    )
  }
  if (mark.kind === 'icon') {
    return (
      <>
        <PlanIconSelect value={mark.icon ?? null} onChange={(v) => v && set('icon', mark.icon ?? null, v)} />
        {size}{turn(mark.rotation ?? 0)}{tint}{layer}
      </>
    )
  }
  return (
    <>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('plan.edit.style')}</Text>
        <SegmentedControl fullWidth value={mark.style ?? 'solid'} onChange={(v) => set('style', mark.style ?? 'solid', v)}
          data={[{ value: 'solid', label: t('plan.edit.styles.solid') }, { value: 'dashed', label: t('plan.edit.styles.dashed') }]} />
      </div>
      <Text size="xs" c="dimmed">{t('plan.edit.wall.help')}</Text>
      {!!mark.points?.length && (
        <Button size="xs" variant="default" onClick={() => void onChange(item, { points: shapeBody(mark, data.size).points }, { points: [] })}>
          {t('plan.edit.wall.straighten', { count: mark.points.length })}
        </Button>
      )}
      {tint}
      {layer}
    </>
  )
}

/** What the right-click menu does to a selection, as buttons, so it can be found without knowing it's there. */
function QuickActions({ canTurn, locked, onLock, onDuplicate, onRotate, onFront, onBack, onFrame }: {
  canTurn: boolean
  /** Whether the selection is all locked; null when nothing in it can be. */
  locked: boolean | null; onLock: () => void
  onDuplicate: () => void; onRotate: () => void; onFront: () => void; onBack: () => void; onFrame: () => void
}) {
  const { t } = useTranslation()
  const icon = (label: string, keys: string, Icon: typeof IconLink, onClick: () => void) => (
    <Tooltip key={label} label={<>{label} <Kbd size="xs">{keys}</Kbd></>}>
      <ActionIcon variant="default" size="lg" aria-label={label} aria-keyshortcuts={keys.replace(/ /g, '+').replace('Ctrl', 'Control')} onClick={onClick}><Icon size={18} /></ActionIcon>
    </Tooltip>
  )
  return (
    <Group gap={4} role="toolbar" aria-label={t('plan.edit.quick')}>
      {icon(t('plan.edit.menu.duplicate'), 'Ctrl D', IconCopy, onDuplicate)}
      {canTurn && icon(t('plan.edit.menu.rotate'), 'R', IconRotateClockwise, onRotate)}
      {icon(t('plan.edit.menu.front'), 'Ctrl ]', IconStackFront, onFront)}
      {icon(t('plan.edit.menu.back'), 'Ctrl [', IconStackBack, onBack)}
      {icon(t('plan.edit.menu.frame'), 'F', IconZoomIn, onFrame)}
      {locked != null && icon(t(locked ? 'plan.edit.menu.unlock' : 'plan.edit.menu.lock'), 'Ctrl ⇧ L', locked ? IconLockOpen : IconLock, onLock)}
    </Group>
  )
}

const ALIGN: [AlignHow, typeof IconLayoutAlignLeft][] = [
  ['left', IconLayoutAlignLeft], ['hcenter', IconLayoutAlignCenter], ['right', IconLayoutAlignRight],
  ['top', IconLayoutAlignTop], ['vcenter', IconLayoutAlignMiddle], ['bottom', IconLayoutAlignBottom],
]

/** Several items selected: line them up, spread them evenly, group or ungroup the blocks. */
function Arrange({ count, grouped, canGroup, onAlign, onDistribute, onGroup }: {
  count: number; grouped: boolean; canGroup: boolean
  onAlign: (how: AlignHow) => void; onDistribute: (axis: 'x' | 'y') => void; onGroup: (join: boolean) => void
}) {
  const { t } = useTranslation()
  const icon = (label: string, Icon: typeof IconLink, onClick: () => void, disabled = false) => (
    <Tooltip key={label} label={label}>
      <ActionIcon variant="default" size="lg" aria-label={label} disabled={disabled} onClick={onClick}><Icon size={18} /></ActionIcon>
    </Tooltip>
  )
  return (
    <div>
      <Text size="sm" fw={500} mb={4}>{t('plan.edit.arrange.title')}</Text>
      <Group gap={4}>
        {ALIGN.map(([how, Icon]) => icon(t(`plan.edit.arrange.${how}`), Icon, () => onAlign(how)))}
        {icon(t('plan.edit.arrange.spreadX'), IconLayoutDistributeHorizontal, () => onDistribute('x'), count < 3)}
        {icon(t('plan.edit.arrange.spreadY'), IconLayoutDistributeVertical, () => onDistribute('y'), count < 3)}
      </Group>
      {(canGroup || grouped) && (
        <Group gap="xs" mt="xs">
          {canGroup && <Button size="xs" variant="default" leftSection={<IconLink size={14} />} onClick={() => onGroup(true)}>{t('plan.edit.menu.group')}</Button>}
          {grouped && <Button size="xs" variant="default" leftSection={<IconUnlink size={14} />} onClick={() => onGroup(false)}>{t('plan.edit.menu.ungroup')}</Button>}
        </Group>
      )}
    </div>
  )
}

// Step names read inside sentences ("Undo: move"); the history list shows them on their own.
const upFirst = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
