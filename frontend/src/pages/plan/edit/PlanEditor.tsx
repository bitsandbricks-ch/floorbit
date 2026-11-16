import { ActionIcon, Anchor, Button, ColorSwatch, Group, Kbd, Menu, NumberInput, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconArrowBackUp, IconArrowForwardUp, IconClipboard, IconCopy, IconCut, IconLayersSubtract, IconStack2, IconTrash } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { SeatViewData } from '@/api/types'
import type { LayerState } from '../layers'
import type { View } from '../model'
import { SeatMap } from '../SeatMap'
import { EditOverlay } from './EditOverlay'
import { type Box, type ItemRef, type Point, allItems, fromPct, movePatch, moved, refKey, sameRef, snappedDelta, toPct } from './geometry'
import { type NewBlock, PlaceBlockDialog, PlaceMarkDialog } from './PlaceDialogs'
import { ToolRail } from './ToolRail'
import { TOOL_KEYS, TOOLS, type Tool } from './tools'
import { useHistory } from './history'
import { type Raw, copies, deltaTo, rawOf } from './clipboard'

const PATH: Record<ItemRef['kind'], string> = { block: '/api/seat-blocks', mark: '/api/plan-marks', switch: '/api/switches' }
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
export function PlanEditor({ data, view, setView, layers, refresh }: {
  data: SeatViewData; view: View; setView: (v: View) => void; layers: LayerState; refresh: () => Promise<unknown>
}) {
  const { t } = useTranslation()
  const [selection, setSelection] = useState<ItemRef[]>([])
  const [drag, setDrag] = useState<{ d: Point } | null>(null)
  // A move the server has saved but the plan hasn't fetched again yet: keep drawing it moved.
  const [pending, setPending] = useState<{ items: ItemRef[]; d: Point; data: SeatViewData } | null>(null)
  const [space, setSpace] = useState(false)
  const [tool, setTool] = useState<Tool>('select')
  // Where a click with the block, text or icon tool asked for something, while its dialog is open.
  const [placing, setPlacing] = useState<{ kind: 'block' | 'text' | 'icon'; at: Point } | null>(null)
  const [menu, setMenu] = useState<{ item: ItemRef | null; x: number; y: number; at: Point | null } | null>(null)
  const history = useHistory()
  const qc = useQueryClient()
  // A deleted item comes back with a new id; steps recorded before still name the old one.
  const alias = useRef(new Map<string, string>())
  const idOf = useCallback((ref: ItemRef) => {
    let id = ref.id
    for (let i = 0; i < 20 && alias.current.has(`${ref.kind}:${id}`); i++) id = alias.current.get(`${ref.kind}:${id}`)!
    return id
  }, [])

  if (pending && pending.data !== data) setPending(null)
  // Selected items that are gone (deleted elsewhere, another hall) drop out of the selection.
  const present = useMemo(() => allItems(data), [data])
  const selected = useMemo(() => selection.filter((r) => present.some((p) => sameRef(p, r))), [selection, present])

  const shown = useMemo(() => {
    let d = data
    if (pending) d = moved(d, pending.items, pending.d)
    if (drag) d = moved(d, selected, drag.d)
    return d
  }, [data, pending, drag, selected])

  const fail = useCallback((err: unknown) => {
    notifications.show({ color: 'down', title: t('plan.edit.failed'), message: err instanceof Error ? err.message : String(err) })
  }, [t])

  const send = useCallback(async (ref: ItemRef, body: Record<string, unknown>) => put(`${PATH[ref.kind]}/${encodeURIComponent(idOf(ref))}`, body), [idOf])

  const moveBy = useCallback(async (items: ItemRef[], d: Point) => {
    if (!items.length || (!d.x && !d.y)) return
    const there = items.map((r) => [r, movePatch(data, r, d), movePatch(data, r, { x: 0, y: 0 })] as const).filter(([, a, b]) => a && b)
    setPending({ items, d, data })
    try {
      await Promise.all(there.map(([r, a]) => send(r, a!)))
      history.push({
        label: t('plan.edit.step.move', { count: there.length }),
        undo: () => Promise.all(there.map(([r, , b]) => send(r, b!))).then(refresh),
        redo: () => Promise.all(there.map(([r, a]) => send(r, a!))).then(refresh),
      })
    } catch (err) {
      setPending(null)
      fail(err)
    }
    await refresh()
  }, [data, send, history, t, refresh, fail])

  /** The items as the server keeps them, to copy, delete with undo, or restack. */
  const snapshot = useCallback(async (items: ItemRef[]): Promise<Saved[]> => {
    const want = items.filter((r) => r.kind !== 'switch')
    const hall = encodeURIComponent(data.hall)
    const [blocks, marks] = await Promise.all([
      want.some((r) => r.kind === 'block') ? get<Record<string, unknown>[]>(`/api/seat-blocks?hall=${hall}`) : Promise.resolve([]),
      want.some((r) => r.kind === 'mark') ? get<{ marks: Record<string, unknown>[] }>(`/api/plan-marks?hall=${hall}`).then((m) => m.marks) : Promise.resolve([]),
    ])
    return want.map((r): Saved | null => {
      const raw = (r.kind === 'block' ? blocks : marks).find((x) => x.id === idOf(r))
      return raw ? { ref: r, raw: rawOf(r.kind, raw) } : null
    }).filter((x): x is Saved => !!x)
  }, [data.hall, idOf])

  const remove = useCallback(async (items: ItemRef[]) => {
    if (!items.some((r) => r.kind !== 'switch')) return
    try {
      const saved = await snapshot(items)
      const drop = (s: Saved[]) => Promise.all(s.map(({ ref }) => del(`${PATH[ref.kind]}/${encodeURIComponent(idOf(ref))}`)))
      const restore = (s: Saved[]) => Promise.all(s.map(async ({ ref, raw }) => {
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

  const copy = useCallback(async (items: ItemRef[], cut = false) => {
    try {
      const saved = await snapshot(items)
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
    await addRaws(copies(clip, d, await blocksInUse()), t('plan.edit.step.paste', { count: clip.length }))
  }, [addRaws, blocksInUse, t])

  const duplicate = useCallback(async (items: ItemRef[]) => {
    try {
      const saved = await snapshot(items)
      // One seat further right and down, so the copy shows next to the original.
      await addRaws(copies(saved.map((s) => s.raw), { x: 2, y: 3.2 }, await blocksInUse()), t('plan.edit.step.duplicate', { count: saved.length }))
    } catch (err) {
      fail(err)
    }
  }, [snapshot, addRaws, blocksInUse, t, fail])

  /** Bring to front (``up``) or send to back: the items' z goes past every other item's. */
  const restack = useCallback(async (items: ItemRef[], up: boolean) => {
    try {
      const all = await snapshot(present)
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
  useEffect(() => {
    const off = () => setSpace(false)
    window.addEventListener('blur', off)
    return () => window.removeEventListener('blur', off)
  }, [])

  const one = selected.length === 1 ? selected[0] : null
  return (
    <div className="fb-plan-layout with-inspector fb-plan-editor" onKeyDownCapture={onKey} onKeyUpCapture={onKeyUp}>
      <div className="fb-edit-stage">
      <ToolRail tool={tool} onTool={setTool} />
      <SeatMap data={shown} view={view} setView={setView} filter="all" selected={null} layers={layers} onSelect={() => {}}
        overlay={(ctx) => (
          <EditOverlay ctx={ctx} data={shown} selection={selected} onSelect={setSelection} space={space} tool={tool}
            onPlace={(at) => { if (tool === 'block' || tool === 'text' || tool === 'icon') setPlacing({ kind: tool, at }) }}
            onLine={drawWall} onBox={(b) => void drawZone(b)}
            onPointer={(p) => { pointer.current = pct(p) }}
            onMenu={(item, x, y) => setMenu({ item, x, y, at: pointer.current })}
            onDrag={(raw, snap, lead) => setDrag({ d: snappedDelta(data, lead, raw, snap) })}
            onDrop={(raw, snap, lead) => { setDrag(null); void moveBy(selected, snappedDelta(data, lead, raw, snap)) }} />
        )} />
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
                <Menu.Divider />
                <Menu.Item leftSection={<IconStack2 size={14} />} rightSection={<Kbd size="xs">Ctrl ]</Kbd>} onClick={() => void restack(selected, true)}>{t('plan.edit.menu.front')}</Menu.Item>
                <Menu.Item leftSection={<IconLayersSubtract size={14} />} rightSection={<Kbd size="xs">Ctrl [</Kbd>} onClick={() => void restack(selected, false)}>{t('plan.edit.menu.back')}</Menu.Item>
                {selected.some((r) => r.kind !== 'switch') && (
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
      <PlaceMarkDialog kind={placing && placing.kind !== 'block' ? placing.kind : null} onClose={() => setPlacing(null)} onCreate={placeMark} />
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
          {selected.length > 0 && selected.some((r) => r.kind !== 'switch') && (
            <Button variant="light" color="down" leftSection={<IconTrash size={16} />} onClick={() => void remove(selected)}>
              {t('plan.edit.delete', { count: selected.filter((r) => r.kind !== 'switch').length })}
            </Button>
          )}
          {!selected.length && (
            <Text size="sm" c="dimmed">{t(tool === 'select' ? 'plan.edit.help' : `plan.edit.hint.${tool}`)}</Text>
          )}
          <Text size="xs" c="dimmed">
            <Kbd size="xs">Del</Kbd> {t('plan.edit.keys.delete')} · <Kbd size="xs">←↑↓→</Kbd> {t('plan.edit.keys.nudge')} · <Kbd size="xs">Alt</Kbd> {t('plan.edit.keys.free')} · <Kbd size="xs">Space</Kbd> {t('plan.edit.keys.pan')}
          </Text>
          <Text size="xs" c="dimmed">{t('plan.edit.keys.more')}</Text>
          <Anchor size="sm" href={`/?hall=${encodeURIComponent(data.hall)}`}>{t('plan.edit.classic')}</Anchor>
        </Stack>
      </Paper>
    </div>
  )
}

function itemTitle(t: (k: string, o?: Record<string, unknown>) => string, data: SeatViewData, ref: ItemRef) {
  if (ref.kind === 'block') return t('plan.edit.kind.block', { name: data.drawing?.shapes.find((s) => s.id === ref.id)?.name || '—' })
  if (ref.kind === 'switch') return t('plan.edit.kind.switch', { name: data.switches.find((w) => w.id === ref.id)?.name ?? '' })
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
        <BlockSize item={item} data={data} onChange={onChange} />
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
      <SegmentedControl fullWidth value={mark.size ?? 'm'} onChange={(v) => set('size', mark.size ?? 'm', v)}
        data={['s', 'm', 'l'].map((x) => ({ value: x, label: t(`plan.edit.mark.sizes.${x}`) }))} />
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

/** Seats per row and rows, from the block as the server keeps it (the drawing has only cells). */
function BlockSize({ data, item, onChange }: {
  data: SeatViewData; item: ItemRef
  onChange: (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const blocks = useQuery({ queryKey: qk.planBlocks(data.hall), queryFn: () => get<{ id: string; cols: number; rows: number }[]>(`/api/seat-blocks?hall=${encodeURIComponent(data.hall)}`) })
  const block = blocks.data?.find((b) => b.id === item.id)
  const [cols, setCols] = useState<number | null>(null)
  const [rows, setRows] = useState<number | null>(null)
  if (!block) return null
  const save = (field: 'cols' | 'rows', v: number | null) => { if (v && v !== block[field]) void onChange(item, { [field]: block[field] }, { [field]: v }).then(() => blocks.refetch()) }
  return (
    <SimpleGrid cols={2}>
      <NumberInput label={t('plan.edit.block.cols')} min={1} max={200} value={cols ?? block.cols} onChange={(v) => setCols(Number(v) || null)}
        onBlur={() => save('cols', cols)} onKeyDown={(e) => { if (e.key === 'Enter') save('cols', cols) }} />
      <NumberInput label={t('plan.edit.block.rows')} min={1} max={50} value={rows ?? block.rows} onChange={(v) => setRows(Number(v) || null)}
        onBlur={() => save('rows', rows)} onKeyDown={(e) => { if (e.key === 'Enter') save('rows', rows) }} />
    </SimpleGrid>
  )
}
