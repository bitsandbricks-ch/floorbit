import { ActionIcon, Anchor, Button, ColorSwatch, Group, Kbd, Menu, Paper, SegmentedControl, Select, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import {
  IconArrowBackUp, IconArrowForwardUp, IconBuildingWarehouse, IconClipboard, IconCopy, IconCut, IconLayersSubtract, IconLayoutAlignBottom, IconLayoutAlignCenter,
  IconLayoutAlignLeft, IconLayoutAlignMiddle, IconLayoutAlignRight, IconLayoutAlignTop, IconLayoutDistributeHorizontal, IconLayoutDistributeVertical,
  IconLink, IconStack2, IconTrash, IconUnlink,
} from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { Cable, Circuit, PlanCable, PlanGroup, PlanMark, PowerMarkers, SeatViewData } from '@/api/types'
import { CableModal, type CableDraft } from '@/components/CableModal'
import { cablePath, useCablePlan } from '../cablePlan'
import type { LayerState } from '../layers'
import type { View } from '../model'
import { SeatMap } from '../SeatMap'
import { BendHandles } from './BendHandles'
import { BlockFields } from './BlockFields'
import { HallsDialog } from './HallsDialog'
import { ItemList } from './ItemList'
import { MarkHandles } from './MarkHandles'
import { shapeBody } from './reshape'
import { PlaceSwitchDialog, type SwitchPick } from './SwitchDialog'
import { type Route, bendsPct } from './bends'
import { EditOverlay } from './EditOverlay'
import { type Box, type ItemRef, type Point, allItems, fromPct, movePatch, moved, nearest, outlineOf, refKey, sameRef, seatAt, snappedDelta, toPct } from './geometry'
import { CableFields, PanelFields, PlacePanelDialog } from './NetworkFields'
import { BoardFields, PlaceBoardDialog } from './PowerFields'
import { type NewBlock, PlaceBlockDialog, PlaceMarkDialog } from './PlaceDialogs'
import { ToolRail } from './ToolRail'
import { TOOL_KEYS, TOOLS, type Tool } from './tools'
import { useHistory } from './history'
import { type Raw, copies, deltaTo, rawOf } from './clipboard'
import { type AlignHow, type Guide, alignMoves, distributeMoves, groupsOf, regrouped, snapToGuides, withGroups } from './arrange'

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
export function PlanEditor({ data, view, setView, layers, refresh: refreshPlan, onHall }: {
  data: SeatViewData; view: View; setView: (v: View) => void; layers: LayerState; refresh: () => Promise<unknown>
  /** Shows another hall, still in Edit mode. */
  onHall: (id: string) => void
}) {
  const { t } = useTranslation()
  const [selection, setSelection] = useState<ItemRef[]>([])
  const [drag, setDrag] = useState<{ d: Point } | null>(null)
  // A move the server has saved but the plan hasn't fetched again yet: keep drawing it moved.
  const [pending, setPending] = useState<{ moves: [ItemRef, Point][]; data: SeatViewData } | null>(null)
  // A mark being resized with its handles: drawn as it is now, and after the drop until the plan comes back.
  const [shaping, setShaping] = useState<{ mark: PlanMark; data: SeatViewData; done?: boolean } | null>(null)
  const [guides, setGuides] = useState<Guide[]>([])
  const [space, setSpace] = useState(false)
  const [tool, setTool] = useState<Tool>('select')
  // Where a click with the block, text or icon tool asked for something, while its dialog is open.
  const [placing, setPlacing] = useState<{ kind: 'block' | 'switch' | 'text' | 'icon' | 'panel' | 'board'; at: Point } | null>(null)
  // The cable form: a new cable (the Cable tool, filled with what was clicked) or one to change.
  const [cableForm, setCableForm] = useState<{ cable: Cable | null; initial?: Partial<CableDraft> } | null>(null)
  const [hallsOpen, setHallsOpen] = useState(false)
  const small = useMediaQuery('(max-width: 48em)')
  const [menu, setMenu] = useState<{ item: ItemRef | null; x: number; y: number; at: Point | null } | null>(null)
  const history = useHistory()
  const qc = useQueryClient()
  // Cables and patch-panel use follow every change: ask for them again with the plan.
  const refresh = useCallback(() => Promise.all([
    refreshPlan(), qc.invalidateQueries({ queryKey: qk.cablePlan(data.hall) }), qc.invalidateQueries({ queryKey: qk.optionsAll }),
    qc.invalidateQueries({ queryKey: qk.power }), qc.invalidateQueries({ queryKey: qk.powerMarkers }),
  ]), [refreshPlan, qc, data.hall])
  const groupsQ = useQuery({ queryKey: qk.planGroups(data.hall), queryFn: () => get<{ groups: PlanGroup[] }>(`/api/plan-groups?hall=${encodeURIComponent(data.hall)}`) })
  const groups = useMemo(() => groupsQ.data?.groups ?? [], [groupsQ.data])
  const saveGroups = useCallback(async (list: PlanGroup[]) => {
    await put('/api/plan-groups', { hall_id: data.hall, groups: list })
    await qc.invalidateQueries({ queryKey: qk.planGroups(data.hall) })
  }, [data.hall, qc])
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
  // Selected items that are gone (deleted elsewhere, another hall) drop out of the selection.
  const present = useMemo(() => [...allItems(data), ...cables.map((c) => ({ kind: 'cable' as const, id: c.ref.cable! }))], [data, cables])
  const selected = useMemo(() => selection.filter((r) => present.some((p) => sameRef(p, r))), [selection, present])

  const shown = useMemo(() => {
    let d = data
    if (pending) for (const [r, m] of pending.moves) d = moved(d, [r], m)
    if (drag) d = moved(d, selected, drag.d)
    if (shaping && d.drawing) {
      const marks = d.drawing.marks?.map((m) => (m.id === shaping.mark.id ? shaping.mark : m))
      d = { ...d, drawing: { ...d.drawing, marks } }
    }
    return d
  }, [data, pending, drag, selected, shaping])

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

  // Boards and cables change with PATCH, the plan's own items with PUT.
  const send = useCallback(async (ref: ItemRef, body: Record<string, unknown>) =>
    (ref.kind === 'board' ? patch : put)(`${PATH[ref.kind]}/${encodeURIComponent(idOf(ref))}`, body), [idOf])

  /** Moves each item by its own amount (drawing units), saved at once, as one step to undo. */
  const moveEach = useCallback(async (moves: [ItemRef, Point][], label?: string) => {
    moves = moves.filter(([, d]) => d.x || d.y)
    if (!moves.length) return
    const there = moves.map(([r, d]) => [r, movePatch(data, r, d), movePatch(data, r, { x: 0, y: 0 })] as const).filter(([, a, b]) => a && b)
    setPending({ moves, data })
    try {
      await Promise.all(there.map(([r, a]) => send(r, a!)))
      history.push({
        label: label ?? t('plan.edit.step.move', { count: there.length }),
        undo: () => Promise.all(there.map(([r, , b]) => send(r, b!))).then(refresh),
        redo: () => Promise.all(there.map(([r, a]) => send(r, a!))).then(refresh),
      })
    } catch (err) {
      setPending(null)
      fail(err)
    }
    await refresh()
  }, [data, send, history, t, refresh, fail])
  const moveBy = useCallback((items: ItemRef[], d: Point) => moveEach(items.map((r) => [r, d] as [ItemRef, Point])), [moveEach])

  /** Puts the selected items in one new group (``join``) or takes them out of theirs. Seat blocks
   *  in an older block group move over to the plan's groups. */
  const regroup = useCallback(async (items: ItemRef[], join: boolean) => {
    const all = withGroups(data, items, groups).filter((r) => r.kind !== 'cable')
    const old = all.filter((r) => r.kind === 'block')
      .map((r) => [r, data.drawing?.shapes.find((x) => x.id === r.id)?.group ?? null] as const).filter(([, g]) => g)
    if (join ? all.length < 2 : !old.length && !groupsOf(groups, all).length) return
    let n = groups.length + 1
    while (groups.some((g) => g.name === t('plan.edit.groups.name', { n }))) n++
    const made = join ? { id: `g-${Math.random().toString(36).slice(2, 10)}`, name: t('plan.edit.groups.name', { n }) } : undefined
    const before = groups, after = regrouped(groups, all, made)
    const apply = async (list: PlanGroup[], undo: boolean) => {
      await Promise.all(old.map(([r, g]) => send(r, { group: undo ? g : null })))
      await saveGroups(list)
    }
    try {
      await apply(after, false)
      history.push({
        label: t(join ? 'plan.edit.step.group' : 'plan.edit.step.ungroup'),
        undo: () => apply(before, true).then(refresh),
        redo: () => apply(after, false).then(refresh),
      })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [data, groups, send, saveGroups, history, t, refresh, fail])

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
  }, [data.hall, idOf, history, t, refresh, fail, snapshot])

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

  const blocksInUse = useCallback(() => get<{ naming?: string; row_start?: string; rows?: number; name?: string }[]>('/api/seat-blocks'), [])
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
        undo: () => Promise.all(moves.map(([r, b]) => send(r, b))).then(refresh),
        redo: () => Promise.all(moves.map(([r, , a]) => send(r, a))).then(refresh),
      })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [snapshot, present, send, history, t, refresh, fail])

  const change = useCallback(async (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => {
    try {
      await send(ref, after)
      history.push({
        label: t('plan.edit.step.change'),
        undo: () => send(ref, before).then(refresh),
        redo: () => send(ref, after).then(refresh),
      })
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [send, history, t, refresh, fail])

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

  /** A cable's drawing: its bends (null: the automatic route) and corners, with undo. */
  const setRoute = useCallback(async (cable: PlanCable, after: { points: [number, number][] | null; corners: 'square' | 'round' }, label: string) => {
    const before = cable.manual ? { points: cable.points.slice(1, -1), corners: cable.corners }
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

  const drawWall = (a: Point, b: Point) => {
    const p = pct(a), q = pct(b)
    void create('mark', '/api/plan-marks', { kind: 'wall', x: p.x, y: p.y, x2: q.x, y2: q.y }, t('plan.edit.step.add.wall'))
  }
  const drawZone = async (box: Box) => {
    const p = pct(box), size = toPct(data.size, { x: box.w, y: box.h })
    const made = await create('mark', '/api/plan-marks', { kind: 'zone', ...p, w: Math.round(size.x * 100) / 100, h: Math.round(size.y * 100) / 100 },
      t('plan.edit.step.add.zone'))
    // A new zone usually gets a name next: select it so the panel shows its label field.
    if (made.length) { setTool('select'); setSelection(made) }
  }

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
    if (e.key === 'Escape' && tool !== 'select') { take(); setTool('select'); return }
    if (!selected.length) return
    if (e.key === 'Escape') { take(); setSelection([]); return }
    if (e.key === 'Delete' || e.key === 'Backspace') { take(); void remove(selected); return }
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
  const dialogOpen = !!placing || !!cableForm
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
    const grid = snappedDelta(data, lead, raw, snap)
    if (!snap) return { d: grid, guides: [] }
    const g = snapToGuides(data, selected, raw, 6 * px, present.filter((r) => r.kind !== 'cable'))
    const on = (axis: 'x' | 'y') => g.guides.some((x) => x.axis === axis)
    return { d: { x: on('x') ? g.d.x : grid.x, y: on('y') ? g.d.y : grid.y }, guides: g.guides }
  }
  const pick = (next: ItemRef[]) => setSelection(withGroups(data, next, groups))
  const grouped = groupsOf(groups, selected).length > 0 || selected.some((r) => r.kind === 'block' && data.drawing?.shapes.find((x) => x.id === r.id)?.group)
  const movable = selected.filter((r) => r.kind !== 'cable')
  // Group again only when that changes something: not one whole group already.
  const canGroup = movable.length > 1 && !(groupsOf(groups, movable).length === 1 && groupsOf(groups, movable)[0].members.every((m) => movable.some((r) => sameRef(r, m))))

  const one = selected.length === 1 ? selected[0] : null
  const oneCable = one?.kind === 'cable' ? cables.find((c) => c.ref.cable === one.id) ?? null : null
  const oneMark = one?.kind === 'mark' ? shown.drawing?.marks?.find((m) => m.id === one.id) ?? null : null
  const markBox = oneMark && one ? outlineOf(shown, one)?.box : null
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
  return (
    <div className="fb-plan-layout with-inspector fb-plan-editor" onKeyDownCapture={onKey} onKeyUpCapture={onKeyUp}>
      <div className="fb-edit-stage">
      <ToolRail tool={tool} onTool={setTool} />
      <SeatMap data={shown} view={view} setView={setView} filter="all" selected={null} layers={layers} onSelect={() => {}} cables={cablePlan?.cables} power={power}
        overlay={(ctx) => (<>
          <EditOverlay ctx={ctx} data={shown} selection={selected} onSelect={pick} together={(r) => withGroups(data, [r], groups)} space={space} tool={tool}
            lines={cables.map((c) => ({ ref: { kind: 'cable', id: c.ref.cable! }, d: cablePath(c.points, data.size, c.corners) }))}
            onPlace={(at, raw) => {
              if (tool === 'block' || tool === 'switch' || tool === 'text' || tool === 'icon' || tool === 'panel' || tool === 'board') setPlacing({ kind: tool, at })
              else if (tool === 'cable') startCable(raw)
            }}
            onLine={drawWall} onBox={(b) => void drawZone(b)}
            onPointer={(p) => { pointer.current = pct(p) }}
            onMenu={(item, x, y) => setMenu({ item, x, y, at: pointer.current })}
            guides={guides}
            onDrag={(raw, snap, lead, px) => { const g = dragTo(raw, snap, lead, px); setGuides(g.guides); setDrag({ d: g.d }) }}
            onDrop={(raw, snap, lead, px) => { setDrag(null); setGuides([]); void moveBy(selected, dragTo(raw, snap, lead, px).d) }} />
          {oneMark && markBox && tool === 'select' && !drag && (
            <MarkHandles key={oneMark.id} ctx={ctx} mark={oneMark} corner={{ x: markBox.x + markBox.w, y: markBox.y + markBox.h }} size={data.size}
              onDraft={(m) => setShaping(m ? { mark: m, data } : null)} onDone={reshaped} />
          )}
          {oneCable && tool === 'select' && (
            <BendHandles key={JSON.stringify(oneCable.points)} ctx={ctx} route={routeOf(oneCable)} cell={data.drawing?.cell ?? 32} path={pathOf}
              onChange={(r) => void setRoute(oneCable, { points: bendsPct(r, data.size), corners: oneCable.corners }, t('plan.edit.step.bend'))} />
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
              </>
            )}
            <Menu.Item leftSection={<IconClipboard size={14} />} rightSection={<Kbd size="xs">Ctrl V</Kbd>} disabled={!readClip()?.length}
              onClick={() => void paste(menu.at ?? undefined)}>{t('plan.edit.menu.paste')}</Menu.Item>
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
                {selected.length > 0 && (
                  <>
                    <Menu.Divider />
                    <Menu.Item color="down" leftSection={<IconTrash size={14} />} rightSection={<Kbd size="xs">Del</Kbd>} onClick={() => void remove(selected)}>{t('plan.edit.menu.delete')}</Menu.Item>
                  </>
                )}
              </>
            )}
          </Menu.Dropdown>
        </Menu>
      )}
      <PlaceBlockDialog opened={placing?.kind === 'block'} onClose={() => setPlacing(null)} onCreate={placeBlock} />
      <PlaceMarkDialog kind={placing && (placing.kind === 'text' || placing.kind === 'icon') ? placing.kind : null} onClose={() => setPlacing(null)} onCreate={placeMark} />
      <PlacePanelDialog opened={placing?.kind === 'panel'} names={(data.panels ?? []).map((p) => p.name)} onClose={() => setPlacing(null)} onCreate={placePanel} />
      <HallsDialog opened={hallsOpen} current={data.hall} onClose={() => setHallsOpen(false)} onOpen={onHall} onChanged={refresh} />
      <PlaceSwitchDialog opened={placing?.kind === 'switch'} onClose={() => setPlacing(null)} onPlace={placeSwitches} />
      <PlaceBoardDialog opened={placing?.kind === 'board'} names={(markers.data?.boards ?? []).map((b) => b.name)} onClose={() => setPlacing(null)} onCreate={placeBoard} />
      {cableForm && <CableModal key={cableForm.cable?.id ?? 'new'} cable={cableForm.cable} canEdit initial={cableForm.initial}
        onClose={() => setCableForm(null)} onDone={(c) => void cableDone(c)} />}
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
            </Group>
          </Group>
          {one && <ItemFields key={refKey(one)} data={data} item={one} onChange={change} />}
          {one?.kind === 'panel' && data.panels?.find((p) => p.name === one.id) && (
            <PanelFields key={`p-${one.id}`} panel={data.panels.find((p) => p.name === one.id)!} onPorts={(a, b) => change(one, { ports: a }, { ports: b })} />
          )}
          {one && oneCable && (
            <CableFields cable={oneCable} onEdit={() => void editCable(one.id)}
              onCorners={(corners) => void setRoute(oneCable, { points: oneCable.manual ? oneCable.points.slice(1, -1) : null, corners }, t('plan.edit.step.corners'))}
              onReset={() => void setRoute(oneCable, { points: null, corners: oneCable.corners }, t('plan.edit.step.autoRoute'))} />
          )}
          {boardSel && (
            <BoardFields key={`b-${boardSel}`} board={boardSel} feedable={feedable.length}
              onAddCircuit={(name) => addCircuit(boardSel, name)} onFeed={(c) => feed(c, feedable)} />
          )}
          {movable.length > 1 && (
            <Arrange count={movable.length} grouped={grouped} canGroup={canGroup}
              onAlign={(how) => void moveEach(alignMoves(data, movable, how), t('plan.edit.step.align'))}
              onDistribute={(axis) => void moveEach(distributeMoves(data, movable, axis), t('plan.edit.step.distribute'))}
              onGroup={(join) => void regroup(selected, join)} />
          )}
          {selected.length > 0 && (
            <Button variant="light" color="down" leftSection={<IconTrash size={16} />} onClick={() => void remove(selected)}>
              {t('plan.edit.delete', { count: selected.length })}
            </Button>
          )}
          {!selected.length && (
            <Text size="sm" c="dimmed">{t(tool === 'select' ? 'plan.edit.help' : `plan.edit.hint.${tool}`)}</Text>
          )}
          {small && !selected.length && <Text size="xs" c="dimmed">{t('plan.edit.smallScreen')}</Text>}
          <ItemList data={data} groups={groups} selected={selected}
            onSelect={(refs, add) => pick(add ? [...selected, ...refs.filter((r) => !selected.some((x) => sameRef(x, r)))] : refs)}
            onRename={(g, name) => void renameGroup(g, name)}
            onUngroup={(g) => void regroup(g.members, false)} />
          <Text size="xs" c="dimmed">
            <Kbd size="xs">Del</Kbd> {t('plan.edit.keys.delete')} · <Kbd size="xs">←↑↓→</Kbd> {t('plan.edit.keys.nudge')} · <Kbd size="xs">Alt</Kbd> {t('plan.edit.keys.free')} · <Kbd size="xs">Space</Kbd> {t('plan.edit.keys.pan')}
          </Text>
          <Text size="xs" c="dimmed">{t('plan.edit.keys.more')}</Text>
          <Group gap="xs">
            <Button size="xs" variant="default" leftSection={<IconBuildingWarehouse size={14} />} onClick={() => setHallsOpen(true)}>{t('plan.edit.halls.button')}</Button>
            <Anchor size="sm" href={`/editor/classic?hall=${encodeURIComponent(data.hall)}`}>{t('plan.edit.classic')}</Anchor>
          </Group>
        </Stack>
      </Paper>
    </div>
  )
}

function itemTitle(t: (k: string, o?: Record<string, unknown>) => string, data: SeatViewData, ref: ItemRef) {
  if (ref.kind === 'block') return t('plan.edit.kind.block', { name: data.drawing?.shapes.find((s) => s.id === ref.id)?.name || '—' })
  if (ref.kind === 'switch') return t('plan.edit.kind.switch', { name: data.switches.find((w) => w.id === ref.id)?.name ?? '' })
  if (ref.kind === 'panel') return t('plan.edit.kind.panel', { name: ref.id })
  if (ref.kind === 'cable') return t('plan.edit.kind.cable')
  if (ref.kind === 'board') return t('plan.edit.kind.board', { name: data.boards?.find((b) => b.id === ref.id)?.name ?? '' })
  const m = data.drawing?.marks?.find((x) => x.id === ref.id)
  return t(`plan.edit.kind.${m?.kind ?? 'text'}`)
}

const LAYER_IDS = ['overview', 'safety', 'network', 'electrical', 'services'] as const
const ZONE_COLORS = ['muted', 'bit', 'trace', 'warn', 'down'] as const

/** One item's fields. Each change is saved on its own (Enter or leaving a text field). */
function ItemFields({ data, item, onChange }: {
  data: SeatViewData; item: ItemRef
  onChange: (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const shape = item.kind === 'block' ? data.drawing?.shapes.find((s) => s.id === item.id) : undefined
  const mark = item.kind === 'mark' ? data.drawing?.marks?.find((m) => m.id === item.id) : undefined
  const [name, setName] = useState(shape?.name ?? mark?.text ?? mark?.label ?? '')
  const set = (field: string, before: unknown, after: unknown) => { if (before !== after) void onChange(item, { [field]: before }, { [field]: after }) }
  const turn = (value: number, field = 'rotation') => (
    <div>
      <Text size="sm" fw={500} mb={4}>{t('plan.edit.rotation')}</Text>
      <SegmentedControl fullWidth value={String(value)} data={['0', '90', '180', '270'].map((v) => ({ value: v, label: `${v}°` }))}
        onChange={(v) => set(field, value, Number(v))} />
    </div>
  )
  if (shape) {
    return (
      <>
        <TextInput label={t('plan.edit.name')} value={name} maxLength={40} onChange={(e) => setName(e.currentTarget.value)} onBlur={() => set('name', shape.name, name)}
          onKeyDown={(e) => { if (e.key === 'Enter') set('name', shape.name, name) }} />
        {turn(shape.rotation)}
        <BlockFields item={item} data={data} onChange={onChange} />
      </>
    )
  }
  if (!mark) return null
  const layer = (
    <Select label={t('plan.edit.layer')} allowDeselect={false} value={mark.layer ?? 'overview'} onChange={(v) => v && set('layer', mark.layer ?? 'overview', v)}
      data={LAYER_IDS.map((l) => ({ value: l, label: t(`plan.edit.layers.${l}`) }))} />
  )
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
        {mark.kind === 'zone' && (
          <div>
            <Text size="sm" fw={500} mb={4}>{t('plan.edit.color')}</Text>
            <Group gap="xs">
              {ZONE_COLORS.map((c) => (
                <Tooltip key={c} label={t(`plan.edit.colors.${c}`)}>
                  <ColorSwatch component="button" type="button" color={`var(--color-${c === 'muted' ? 'muted' : c})`} size={26}
                    aria-label={t(`plan.edit.colors.${c}`)} aria-pressed={(mark.color ?? 'muted') === c} onClick={() => set('color', mark.color ?? 'muted', c)}
                    style={{ outline: (mark.color ?? 'muted') === c ? '2px solid var(--color-fg)' : undefined, outlineOffset: 2 }} />
                </Tooltip>
              ))}
            </Group>
          </div>
        )}
        {layer}
      </>
    )
  }
  if (mark.kind === 'icon') return <>{size}{turn(mark.rotation ?? 0)}{layer}</>
  return (
    <>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('plan.edit.style')}</Text>
        <SegmentedControl fullWidth value={mark.style ?? 'solid'} onChange={(v) => set('style', mark.style ?? 'solid', v)}
          data={[{ value: 'solid', label: t('plan.edit.styles.solid') }, { value: 'dashed', label: t('plan.edit.styles.dashed') }]} />
      </div>
      {layer}
    </>
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
