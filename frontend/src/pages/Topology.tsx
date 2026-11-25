import {
  ActionIcon, Alert, Autocomplete, Badge, Button, Drawer, Group, Menu, Modal, Paper, ScrollArea, Select, SimpleGrid, Stack, Tabs, Text, TextInput, Title, Tooltip, UnstyledButton,
} from '@mantine/core'
import { useElementSize, useHotkeys } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import {
  IconAlertTriangle, IconDownload, IconFocus2, IconLine, IconMinus, IconPhoto, IconPlus, IconPointer, IconRadar, IconVectorBezier2, IconWand,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { LinkSuggestion, SwitchLink, SwitchPort, Topology as TopologyData, TopologyNode, TopologyUplink } from '@/api/types'
import { Attribution } from '@/components/Attribution'
import { download, standaloneSvg, svgToPng } from './plan/exportImage'
import { PlanKey } from './plan/PlanKey'
import { type Box as ViewBox, bounds, framed, toDiagram, zoomAt } from './topology/camera'
import { GLYPH_Y, NODE_H, NODE_W, type Placed, arranged, gbit, layout, placeUplinks, routes } from './topology/layout'
import { DeviceGlyph, UplinkGlyph } from './topology/glyphs'
import { UPLINK_WIDTH } from './plan/linkLook'
import './Topology.css'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { ConfirmButton, StatusBadge } from '@bitsandbricks/ui'

const READABLE = 1 // the smallest scale the opening view shows names at: 11px, as on the plan
// Fitted at half of READABLE or more, the opening view shows everything, like the Map view (#1439):
// names a little small beat a picture cut off at both edges. Only a big network opens at READABLE.
const NEARLY = 0.5
const ROOMY = 1.6 // the largest: a small network doesn't blow up to fill the page (#1331)
const NAME_MAX = 10
const short = (name: string) => (name.length > NAME_MAX ? `${name.slice(0, NAME_MAX - 1)}…` : name)
/** The plan's link classes (styles/plan.css .uplink): one colour per media, single-mode fiber its own (#1334). */
const linkClass = (l: SwitchLink) => `uplink m-${l.media || mediaOf(l.type) || 'none'} t-${l.type || 'none'}${l.issue ? ` ${l.issue}` : ''}`
function mediaOf(type: string) {
  return type.startsWith('cat') ? 'copper' : type.startsWith('fiber') ? 'fiber' : type === 'dac' ? 'dac' : ''
}

type Picked = { kind: 'link'; id: string } | { kind: 'node'; name: string } | { kind: 'uplink'; id: string } | null
type Draft = Partial<SwitchLink> & { id?: string }
type SideTab = 'problems' | 'found'

export interface TopologyViewProps {
  phone: boolean
  /** The floor plan's side panel is open (the ] key and its button in the top bar). */
  sideOpen: boolean
  /** The switch open in the plan's switch panel (?switch=), and that panel. */
  switchSel: string | null
  switchPanel: ReactNode
  /** Open a switch in the plan's panel, or close it (null). */
  onSwitch: (name: string | null) => void
}

/** The network's links between switches (issue #468), as the floor plan's third view (#1330): the
 *  plan's grid, glyphs, tool rail, zoom buttons and side panel. Type and speed, down or slower than
 *  planned, and what LLDP sees that no link explains yet. The crew drags glyphs where they belong
 *  (kept for everyone), draws a link by picking two, and it saves as PNG or SVG. */
export default function TopologyView({ phone, sideOpen, switchSel, switchPanel, onSwitch }: TopologyViewProps) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const q = useQuery({ queryKey: qk.topology, queryFn: () => get<TopologyData>('/api/links'), refetchInterval: 30_000 })
  const [picked, setPicked] = useState<Picked>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [wire, setWire] = useState<{ a?: string } | null>(null)
  const [tab, setTab] = useState<SideTab>('problems')
  const [cam, setCam] = useState<ViewBox | null>(null) // null: the opening view (see `start`)
  const { ref: paneRef, width: paneWidth, height: paneHeight } = useElementSize()
  const [drag, setDrag] = useState<{ key: string; x: number; y: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const gesture = useRef<{ kind: 'pan' | 'node'; key?: string; sx: number; sy: number; ox: number; oy: number; cam: ViewBox; moved: boolean } | null>(null)
  const moved = useRef(false) // the last press dragged something: its click isn't a pick
  const data = q.data
  const auto = useMemo(() => (data ? layout(data.nodes, data.links) : null), [data])
  const placed = useMemo(() => (auto ? arranged(auto, data?.layout) : null), [auto, data?.layout])
  const lines = useMemo(() => (placed && data ? placeUplinks(placed, data.uplinks ?? []) : null), [placed, data])
  // where a glyph is drawn: being dragged, or where the layout puts it
  const spot = useCallback((p: Placed) => (drag && drag.key === p.node.name.toLowerCase() ? { x: drag.x, y: drag.y } : { x: p.x, y: p.y }), [drag])
  const base = useMemo<ViewBox | null>(() => {
    if (!placed || !lines) return null
    const boxes = [...placed.placed.values()].map((p) => ({ ...spot(p), w: NODE_W, h: NODE_H })).map((b) => ({ ...b, x: b.x + lines.dx, y: b.y + lines.dy }))
    return bounds([...boxes, ...lines.boxes.map((b) => ({ x: b.x, y: b.y - 20, w: NODE_W, h: NODE_H + 20 }))], 24)
  }, [placed, lines, spot])
  const sized = paneWidth > 0 && paneHeight > 0
  // Show everything, but no bigger than ROOMY: three switches stay three small glyphs.
  // (Before the pane is measured, and in tests, the picture as it is.)
  const whole = useMemo(() => (base && sized ? framed(base, paneWidth, paneHeight, 0, ROOMY) : base), [base, sized, paneWidth, paneHeight])
  // Fitted, a big network is too small to read (#1050): it opens at READABLE from its top instead.
  // One that nearly fits opens whole: cutting off a few names at both edges reads worse.
  const start = useMemo(() => {
    if (!base || !sized) return base
    return Math.min(paneWidth / base.w, paneHeight / base.h) >= NEARLY * READABLE ? whole : framed(base, paneWidth, paneHeight, READABLE, ROOMY)
  }, [base, sized, paneWidth, paneHeight, whole])
  // The camera keeps the pane's shape, so the grid reaches every edge; a resized pane widens it.
  const view = useMemo(() => {
    if (!cam || !sized) return cam ?? start
    const h = (cam.w * paneHeight) / paneWidth
    return { ...cam, y: cam.y + (cam.h - h) / 2, h }
  }, [cam, start, sized, paneWidth, paneHeight])
  const hasKids = useMemo(() => new Set(placed ? placed.parent.values() : []), [placed])
  const gridId = `topo-grid-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  const runs = useMemo(() => (placed ? routes(data?.links ?? [], placed.parent, (k) => { const p = placed.placed.get(k); return p ? spot(p) : undefined }) : null), [placed, data?.links, spot])
  const uplink = picked?.kind === 'uplink' ? data?.uplinks.find((u) => u.id === picked.id) : undefined
  const link = picked?.kind === 'link' ? data?.links.find((l) => l.id === picked.id) : undefined
  const node = picked?.kind === 'node' ? data?.nodes.find((n) => n.name === picked.name) : undefined
  const problems = data?.links.filter((l) => l.issue || l.lldp?.state === 'other') ?? []
  const arrangedByCrew = !!data?.layout && Object.keys(data.layout).length > 0

  const saveLayout = useMutation({
    mutationFn: (positions: Record<string, { x: number; y: number }>) => put<{ layout: Record<string, { x: number; y: number }> }>('/api/links/layout', { positions }),
    onSuccess: (r) => qc.setQueryData<TopologyData>(qk.topology, (old) => (old ? { ...old, layout: r.layout } : old)),
    onSettled: () => setDrag(null),
  })
  const resetLayout = useMutation({
    mutationFn: () => del('/api/links/layout'),
    onSuccess: () => { qc.setQueryData<TopologyData>(qk.topology, (old) => (old ? { ...old, layout: {} } : old)); setCam(null) },
  })

  // The wheel zooms around the pointer; React's onWheel is passive, so it can't keep the page from scrolling.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !view || !base) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const at = toDiagram(view, svg.getBoundingClientRect(), e.clientX, e.clientY)
      setCam(zoomAt(view, base, Math.exp(-e.deltaY * 0.0015), at))
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [view, base])

  const zoomBy = (factor: number) => { if (view && base) setCam(zoomAt(view, base, factor, { x: view.x + view.w / 2, y: view.y + view.h / 2 })) }
  const dialogOpen = () => !!document.querySelector('[role="dialog"]')
  const pick = (p: Picked) => { setPicked(p); if (p) onSwitch(null) }
  // Esc ends drawing a link, then closes what is open here.
  useHotkeys([['Escape', () => { if (dialogOpen()) return; if (wire) setWire(null); else if (picked) setPicked(null) }]])
  // With the diagram focused, + and − zoom and 0 shows everything, as on the plan.
  const onKey = (e: React.KeyboardEvent) => {
    const keys: Record<string, () => void> = { '+': () => zoomBy(1.4), '=': () => zoomBy(1.4), '-': () => zoomBy(1 / 1.4), '0': () => setCam(whole) }
    if (keys[e.key]) { e.preventDefault(); keys[e.key]() }
  }
  // A switch opens the plan's own switch panel; routers, firewalls and links open theirs here.
  const pickNode = (name: string, role: string) => {
    if (wire) {
      if (!wire.a) setWire({ a: name })
      else if (wire.a !== name) { setDraft({ a: wire.a, b: name }); setWire(null) }
      return
    }
    if (role === 'switch') { setPicked(null); onSwitch(name) } else pick({ kind: 'node', name })
  }
  const down = (e: React.PointerEvent<SVGSVGElement>, key?: string) => {
    if (!view || e.button !== 0) return
    const p = key ? placed?.placed.get(key) : undefined
    moved.current = false
    gesture.current = { kind: key ? 'node' : 'pan', key, sx: e.clientX, sy: e.clientY, ox: p?.x ?? 0, oy: p?.y ?? 0, cam: view, moved: false }
  }
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const g = gesture.current, svg = svgRef.current
    if (!g || !svg) return
    const rect = svg.getBoundingClientRect()
    const dx = ((e.clientX - g.sx) / (rect.width || 1)) * g.cam.w, dy = ((e.clientY - g.sy) / (rect.height || 1)) * g.cam.h
    if (!g.moved && Math.hypot(e.clientX - g.sx, e.clientY - g.sy) < 4) return
    if (!g.moved) { g.moved = true; svg.setPointerCapture?.(e.pointerId) }
    if (g.kind === 'pan') setCam({ ...g.cam, x: g.cam.x - dx, y: g.cam.y - dy })
    else if (g.key) setDrag({ key: g.key, x: g.ox + dx, y: g.oy + dy })
  }
  const up = () => {
    const g = gesture.current
    gesture.current = null
    moved.current = !!g?.moved
    if (!g?.moved || g.kind !== 'node' || !drag || !placed) return
    // Every glyph's place goes with it, so the picture stays as it is when one is moved.
    const positions = Object.fromEntries([...placed.placed].map(([k, p]) => [k, k === drag.key ? { x: drag.x, y: drag.y } : { x: p.x, y: p.y }]))
    saveLayout.mutate(positions)
  }
  const clickedAfterMove = () => moved.current

  const exportAs = async (as: 'png' | 'svg') => {
    const svg = svgRef.current
    if (!svg || !base) return
    const shown = svg.getAttribute('viewBox')
    svg.setAttribute('viewBox', `${base.x} ${base.y} ${base.w} ${base.h}`) // the whole picture, not just the zoomed part
    try {
      const out = standaloneSvg(svg, Math.max(1600, base.w * 2))
      const page = getComputedStyle(document.body).backgroundColor || '#fff'
      download(as === 'svg' ? new Blob([out.text], { type: 'image/svg+xml' }) : await svgToPng(out.text, out.width, out.height, page), `topology.${as}`)
    } catch {
      notifications.show({ color: 'down', message: t('topology.exportFailed') })
    } finally {
      if (shown) svg.setAttribute('viewBox', shown)
    }
  }

  const own = uplink ? <UplinkPanel uplink={uplink} />
    : link ? <LinkPanel link={link} canEdit={canEdit} onEdit={() => setDraft(link)} onGone={() => setPicked(null)} />
    : node ? <NodePanel name={node.name} role={node.role} status={node.status} links={data!.links.filter((l) => l.a === node.name || l.b === node.name)}
      onPick={(id) => pick({ kind: 'link', id })} />
      : null
  const inspector = switchSel ? switchPanel : own && (
    <Stack gap="sm" className="fb-inspector">
      <Group justify="flex-end"><Button variant="subtle" size="compact-sm" onClick={() => setPicked(null)}>{t('plan.close')}</Button></Group>
      {own}
    </Stack>
  )
  const showSide = !phone && (!!inspector || sideOpen)
  const chosenName = switchSel ?? (picked?.kind === 'node' ? picked.name : null)

  return (
    <>
      <div className={`fb-plan-layout fb-topology-view${showSide ? ' with-inspector' : ''}`}>
        <div className="fb-edit-stage">
          <Stack gap={4} className="fb-edit-rail" role="toolbar" aria-orientation="vertical" aria-label={t('topology.tools')}>
            <RailButton label={t('topology.select')} icon={IconPointer} pressed={!wire} onClick={() => setWire(null)} />
            {canEdit && <>
              <RailButton label={t(wire ? 'topology.drawCancel' : 'topology.draw')} icon={IconLine} pressed={!!wire} onClick={() => setWire(wire ? null : {})} />
              <RailButton label={t('topology.add')} icon={IconPlus} onClick={() => setDraft({})} />
              {arrangedByCrew && (
                <Menu position="right-start" withinPortal>
                  <Menu.Target>
                    <ActionIcon size="lg" variant="subtle" aria-label={t('topology.arrange')} title={t('topology.arrange')}><IconWand size={18} aria-hidden="true" /></ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown maw={260}>
                    <Text size="sm" p="xs">{t('topology.arrangeQuestion')}</Text>
                    <Menu.Item onClick={() => resetLayout.mutate()}>{t('topology.arrange')}</Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              )}
            </>}
            <div className="fb-edit-rail-sep" role="separator" />
            <Menu position="right-start" withinPortal>
              <Menu.Target>
                <ActionIcon size="lg" variant="subtle" aria-label={t('topology.export')} title={t('topology.export')}><IconDownload size={18} aria-hidden="true" /></ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPhoto size={14} />} onClick={() => void exportAs('png')}>{t('topology.exportPng')}</Menu.Item>
                <Menu.Item leftSection={<IconVectorBezier2 size={14} />} onClick={() => void exportAs('svg')}>{t('topology.exportSvg')}</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Stack>
          <div className="fb-ws-canvas fb-topology-canvas" ref={paneRef}>
            {q.isPending && <div className="fb-ws-pad"><LoadingState /></div>}
            {q.error && <div className="fb-ws-pad"><ErrorBanner error={q.error} onRetry={() => void q.refetch()} /></div>}
            {data && data.links.length === 0 && (
              <div className="fb-ws-pad"><Paper withBorder radius="lg" p="md"><Text c="dimmed">{t(canEdit ? 'topology.emptyEdit' : 'topology.empty')}</Text></Paper></div>
            )}
            {data && placed && lines && view && base && data.links.length > 0 && (
              <svg ref={svgRef} role="img" aria-label={t('topology.diagram', { count: data.links.length })}
                viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} className="fb-plan fb-topology"
                tabIndex={0} onKeyDown={onKey} onPointerDown={(e) => down(e)} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { gesture.current = null; setDrag(null) }}
                style={{ cursor: wire ? 'crosshair' : 'grab' }}>
                <TopologyGrid id={gridId} view={view} base={base} scale={paneWidth / view.w} />
                {lines.boxes.map(({ uplink: u, x, y, to }) => {
                  const chosen = picked?.kind === 'uplink' && picked.id === u.id
                  const toAt = spot(to)
                  const cx = x + NODE_W / 2, tx = toAt.x + lines.dx + NODE_W / 2, ty = toAt.y + lines.dy + GLYPH_Y - 8
                  const mid = (y + GLYPH_Y + 8 + ty) / 2
                  return (
                    <g key={u.id} className={`fb-uplink${chosen ? ' chosen' : ''}`} data-status={u.status} onClick={() => { if (!clickedAfterMove()) pick({ kind: 'uplink', id: u.id }) }} style={{ cursor: 'pointer' }}>
                      <title>{`${u.name}: ${u.device} ${u.port} · ${t(`topology.uplinkStatus.${u.status}`)}`}</title>
                      <path className="line" d={`M${cx} ${y + GLYPH_Y + 8}V${mid}H${tx}V${ty}`} strokeDasharray={u.status === 'down' ? '6 4' : undefined} />
                      <rect x={x} y={y} width={NODE_W} height={NODE_H} fill="transparent" />
                      <g transform={`translate(${cx} ${y + GLYPH_Y})`}><UplinkGlyph /></g>
                      <text x={cx} y={y + GLYPH_Y - 17}>{short(u.name)}</text>
                    </g>
                  )
                })}
                <g transform={`translate(${lines.dx} ${lines.dy})`}>
                {/* Problem links first, so a shared trunk shows the run's colour and only its own drop the problem. */}
                {runs && [...data.links].sort((x, y) => Number(!x.issue) - Number(!y.issue)).map((l) => {
                  const r = runs.lines.find((x) => x.id === l.id)
                  if (!r) return null
                  const chosen = picked?.kind === 'link' && picked.id === l.id
                  return (
                    <g key={l.id} data-link={l.id} onClick={() => { if (!clickedAfterMove() && !wire) pick({ kind: 'link', id: l.id }) }} style={{ cursor: 'pointer' }}>
                      <title>{`${l.a} ${l.a_port} – ${l.b} ${l.b_port}${l.speed ? ` · ${l.speed}G` : ''}`}</title>
                      <path className="uplink-hit" d={r.d} vectorEffect="non-scaling-stroke" />
                      <path className={linkClass(l)} d={r.d} strokeWidth={(UPLINK_WIDTH[l.speed ?? 0] ?? 1.5) + (chosen ? 2 : 0)} vectorEffect="non-scaling-stroke"
                        strokeDasharray={l.type === '' ? '2 3' : undefined} strokeLinecap="round" />
                    </g>
                  )
                })}
                {runs?.counts.map((c) => (
                  <g key={`${c.x} ${c.y}`} className="cable-count" transform={`translate(${c.x} ${c.y})`} aria-hidden="true">
                    <circle r={9} /><text dy="0.35em" fontSize={10}>{c.count}</text>
                  </g>
                ))}
                {[...placed.placed.entries()].map(([key, p]) => {
                  const chosen = chosenName === p.node.name || wire?.a === p.node.name
                  const at = spot(p)
                  const status = p.node.status
                  return (
                    <g key={p.node.id} transform={`translate(${at.x + NODE_W / 2} ${at.y + GLYPH_Y})`} data-node={p.node.name} data-status={status}
                      className={`sw sw-${status}${status === 'offline' ? ' down' : ''}`}
                      onPointerDown={(e) => { e.stopPropagation(); if (canEdit && !wire) down(e as unknown as React.PointerEvent<SVGSVGElement>, key); else { gesture.current = null; moved.current = false } }}
                      onClick={() => { if (!clickedAfterMove()) pickNode(p.node.name, p.node.role) }}
                      style={{ cursor: wire ? 'crosshair' : canEdit ? 'move' : 'pointer' }}>
                      <title>{`${p.node.name}: ${t(`topology.status.${status}`)}`}</title>
                      <rect x={-NODE_W / 2} y={-GLYPH_Y} width={NODE_W} height={NODE_H} fill="transparent" />
                      {chosen && <circle className="sw-focus" r={17} />}
                      <DeviceGlyph role={p.node.role} status={status} />
                      {/* A glyph with a run going down has its name beside it, clear of the trunk. */}
                      {hasKids.has(key)
                        ? <text className="side" x={p.node.role === 'router' ? -19 : -16} y={4}>{short(p.node.name)}</text>
                        : <text y={NODE_H - GLYPH_Y - 4}>{short(p.node.name)}</text>}
                    </g>
                  )
                })}
                </g>
              </svg>
            )}
            {wire && <div className="fb-topology-hint" role="status">{wire.a ? t('topology.drawSecond', { a: wire.a }) : t('topology.drawFirst')}</div>}
            {data && data.links.length > 0 && (
              <div className="fb-ws-corner">
                {saveLayout.error && <Alert color="down" role="alert" py={6}>{saveLayout.error.message}</Alert>}
                <PlanKey><Legend links={data.links} /></PlanKey>
              </div>
            )}
            {view && base && (
              <Group gap={4} className="fb-plan-zoom fb-no-print">
                <Tooltip label={t('topology.zoomIn')}><ActionIcon variant="default" aria-label={t('topology.zoomIn')} onClick={() => zoomBy(1.4)}><IconPlus size={16} /></ActionIcon></Tooltip>
                <Tooltip label={t('topology.zoomOut')}><ActionIcon variant="default" aria-label={t('topology.zoomOut')} onClick={() => zoomBy(1 / 1.4)}><IconMinus size={16} /></ActionIcon></Tooltip>
                <Tooltip label={t('topology.fit')}><ActionIcon variant="default" aria-label={t('topology.fit')} onClick={() => setCam(whole)}><IconFocus2 size={16} /></ActionIcon></Tooltip>
              </Group>
            )}
          </div>
        </div>
        {showSide && (inspector
          ? <aside className="fb-ws-panel" aria-label={t('plan.side.label')}>{inspector}</aside>
          : <TopologySide tab={tab} onTab={setTab} data={data} problems={problems} loose={placed?.loose.map((n) => n.name) ?? []}
            canEdit={canEdit} onLink={(id) => pick({ kind: 'link', id })} onAdd={(s) => setDraft(fromSuggestion(s))} />)}
      </div>
      {phone && (
        <Drawer opened={!!inspector} onClose={() => { setPicked(null); onSwitch(null) }} position="bottom" size="55%" withCloseButton={false}
          title={null} aria-label={switchSel ?? (link ? t('topology.link') : node?.name ?? uplink?.name ?? '')}>{inspector}</Drawer>
      )}
      {draft && data && <LinkModal draft={draft} data={data} onClose={() => setDraft(null)} />}
    </>
  )
}

function RailButton({ label, icon: Icon, pressed, onClick }: { label: string; icon: typeof IconPointer; pressed?: boolean; onClick: () => void }) {
  return (
    <Tooltip position="right" label={label}>
      <ActionIcon size="lg" variant={pressed ? 'filled' : 'subtle'} aria-label={label} aria-pressed={pressed} onClick={onClick}>
        <Icon size={18} aria-hidden="true" />
      </ActionIcon>
    </Tooltip>
  )
}

/** The side panel while nothing is open, like the plan's: what is wrong with the links, and what
 *  LLDP sees that no link explains yet. */
function TopologySide({ tab, onTab, data, problems, loose, canEdit, onLink, onAdd }: {
  tab: SideTab; onTab: (t: SideTab) => void; data?: TopologyData; problems: SwitchLink[]; loose: string[]
  canEdit: boolean; onLink: (id: string) => void; onAdd: (s: LinkSuggestion) => void
}) {
  const { t } = useTranslation()
  const found = data?.suggestions ?? []
  return (
    <aside className="fb-ws-panel tabs" aria-label={t('plan.side.label')}>
      <Tabs value={tab} onChange={(v) => v && onTab(v as SideTab)} keepMounted={false} className="fb-side-tabs">
        <Tabs.List grow>
          <Tabs.Tab value="problems" leftSection={<IconAlertTriangle size={14} />}>
            {t('topology.side.problems')}{problems.length ? <Badge size="xs" color="down" ml={6}>{problems.length}</Badge> : null}</Tabs.Tab>
          <Tabs.Tab value="found" leftSection={<IconRadar size={14} />}>
            {t('topology.side.found')}{found.length ? <Badge size="xs" color="gray" ml={6}>{found.length}</Badge> : null}</Tabs.Tab>
        </Tabs.List>
        <ScrollArea className="fb-side-body" type="auto">
          <Tabs.Panel value="problems" p="md">
            <Stack gap="xs">
              {!problems.length && <Text size="sm" c="dimmed">{t('topology.side.allGood')}</Text>}
              {problems.map((l) => (
                <UnstyledButton key={l.id} className="fb-side-row" onClick={() => onLink(l.id)}>
                  <Text size="sm" c={l.issue === 'down' ? 'down' : l.issue ? 'warn' : undefined}>
                    {l.issue
                      ? t(`topology.issue.${l.issue}`, { a: `${l.a} ${l.a_port}`, b: `${l.b} ${l.b_port}`, planned: `${l.speed}G`, actual: gbit(l.speed_bps) })
                      : t('topology.issue.miswired', { a: `${l.a} ${l.a_port}`, b: `${l.b} ${l.b_port}`, ...seenAt(l) })}
                  </Text>
                </UnstyledButton>
              ))}
              {loose.length > 0 && <Text size="xs" c="dimmed" mt="sm">{t('topology.loose', { names: loose.join(', ') })}</Text>}
              <Text size="xs" c="dimmed" mt="sm">{t(canEdit ? 'topology.pickHintEdit' : 'topology.pickHint')} {t(canEdit ? 'topology.howEdit' : 'topology.how')}</Text>
            </Stack>
          </Tabs.Panel>
          <Tabs.Panel value="found" p="md">
            <Stack gap={6}>
              <Text size="sm" c="dimmed">{found.length ? t('topology.suggestionsHint') : t('topology.side.nothingFound')}</Text>
              {found.map((s) => (
                <Group key={`${s.a}${s.a_port}${s.b}${s.b_port}`} justify="space-between" wrap="nowrap" gap="xs">
                  <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>
                    {s.a} {s.a_port} – {s.b} {s.b_port}{s.protocol ? ` (${s.protocol.toUpperCase()})` : ''}
                  </Text>
                  {canEdit && <Button size="compact-sm" variant="default" onClick={() => onAdd(s)}>{t('topology.addThis')}</Button>}
                </Group>
              ))}
            </Stack>
          </Tabs.Panel>
        </ScrollArea>
      </Tabs>
      <div className="fb-side-foot"><Attribution compact version /></div>
    </aside>
  )
}

/** Where a wrong patch was seen and what is on the other end, for the texts. */
function seenAt(l: SwitchLink) {
  const at = l.lldp?.at ?? 'a'
  return { here: `${l[at]} ${l[`${at}_port`]}`, there: `${l.lldp?.remote ?? ''} ${l.lldp?.remote_port ?? ''}`.trim() }
}

function fromSuggestion(s: LinkSuggestion): Draft {
  return { a: s.a, a_port: s.a_port, b: s.b, b_port: s.b_port, speed: s.speed, type: '' }
}

/** Only what the diagram draws: a legend entry for copper with no copper link sends people looking. */
function Legend({ links }: { links: SwitchLink[] }) {
  const { t } = useTranslation()
  const has = (pred: (l: SwitchLink) => boolean) => links.some(pred)
  const all: [boolean, string, string][] = [
    [has((l) => l.type.startsWith('cat')), t('topology.media.copper'), 'uplink m-copper'],
    [has((l) => l.type === 'fiber-sm'), t('topology.types.fiber-sm'), 'uplink m-fiber t-fiber-sm'],
    [has((l) => l.type === 'fiber-mm'), t('topology.types.fiber-mm'), 'uplink m-fiber'],
    [has((l) => l.type === 'dac'), t('topology.types.dac'), 'uplink m-dac'],
    [has((l) => l.issue === 'slow'), t('topology.slow'), 'uplink slow'],
    [has((l) => l.issue === 'down'), t('topology.down'), 'uplink down'],
  ]
  const items = all.filter(([shown]) => shown).map(([, ...rest]) => rest as [string, string])
  const speeds = new Set(links.map((l) => l.speed).filter(Boolean)).size
  return (
    <Stack gap={4}>
      {items.map(([label, look]) => (
        <Group key={label} gap={8} wrap="nowrap">
          <svg width={24} height={8} aria-hidden="true" className="fb-plan fb-topology"><line className={look} x1={1} y1={4} x2={23} y2={4} strokeWidth={3} /></svg>
          <Text size="xs" c="dimmed">{label}</Text>
        </Group>
      ))}
      {speeds > 1 && <Text size="xs" c="dimmed">{t('topology.thicker')}</Text>}
    </Stack>
  )
}

function LinkPanel({ link: l, canEdit, onEdit, onGone }: { link: SwitchLink; canEdit: boolean; onEdit: () => void; onGone: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => del(`/api/links/${l.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.topology }); onGone() },
  })
  const tone = l.issue === 'down' ? 'down' : l.issue === 'slow' ? 'warn' : l.state === 'up' ? 'up' : 'gray'
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{t('topology.link')}</Title>
        <Badge color={tone} variant="light">{l.issue ? t(`topology.${l.issue}`) : t(`topology.state.${l.state}`)}</Badge>
      </Group>
      <Text size="sm" ff="monospace">{l.a} {l.a_port}</Text>
      <Text size="sm" ff="monospace">{l.b} {l.b_port}</Text>
      <SimpleGrid cols={2} spacing={4}>
        <Text size="sm" c="dimmed">{t('topology.type')}</Text><Text size="sm">{l.type ? t(`topology.types.${l.type}`) : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.planned')}</Text><Text size="sm">{l.speed ? `${l.speed}G` : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.actual')}</Text><Text size="sm">{gbit(l.speed_bps) || '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.lldp')}</Text>
        <Text size="sm" className={l.lldp?.state === 'other' ? 'fb-tone-warn' : undefined}>
          {l.lldp ? t(`topology.lldpState.${l.lldp.state}`, seenAt(l)) : '–'}
        </Text>
      </SimpleGrid>
      {l.note && <Text size="sm">{l.note}</Text>}
      {canEdit && (
        <Group gap="xs" mt={4}>
          <Button size="compact-sm" variant="default" onClick={onEdit}>{t('topology.edit')}</Button>
          <ConfirmButton size="compact-sm" variant="subtle" danger label={t('topology.remove')}
            question={t('topology.removeQuestion', { a: l.a, b: l.b })} onConfirm={() => remove.mutate()} />
        </Group>
      )}
    </Stack>
  )
}

function NodePanel({ name, role, status, links, onPick }: {
  name: string; role: string; status: TopologyNode['status']; links: SwitchLink[]; onPick: (id: string) => void
}) {
  const { t } = useTranslation()
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{name}</Title>
        <StatusBadge size="md" state={status} label={t(`topology.status.${status}`)} />
      </Group>
      <Text size="sm" c="dimmed">{t(`topology.roles.${role}`, { defaultValue: role })} · {t('topology.links', { count: links.length })}</Text>
      {links.map((l) => {
        const [mine, other, otherPort] = l.a === name ? [l.a_port, l.b, l.b_port] : [l.b_port, l.a, l.a_port]
        return (
          <Button key={l.id} variant="subtle" size="compact-sm" justify="space-between" onClick={() => onPick(l.id)}
            color={l.issue === 'down' ? 'down' : l.issue === 'slow' ? 'warn' : undefined}
            rightSection={l.speed ? `${l.speed}G` : undefined} styles={{ label: { whiteSpace: 'normal', textAlign: 'left' } }}>
            {mine} → {other} {otherPort}
          </Button>
        )
      })}
    </Stack>
  )
}

function LinkModal({ draft, data, onClose }: { draft: Draft; data: TopologyData; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    a: draft.a ?? '', a_port: draft.a_port ?? '', b: draft.b ?? '', b_port: draft.b_port ?? '',
    type: draft.type ?? '', speed: draft.speed ? String(draft.speed) : '', note: draft.note ?? '',
  })
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, speed: form.speed ? Number(form.speed) : null }
      return draft.id ? put(`/api/links/${draft.id}`, body) : post('/api/links', body)
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.topology }); onClose() },
  })
  const switches = data.nodes.map((n) => n.name)
  return (
    <Modal opened onClose={onClose} title={draft.id ? t('topology.editTitle') : t('topology.add')} size="lg">
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Select label={t('topology.from')} data={switches} searchable value={form.a || null} onChange={(v) => set({ a: v ?? '' })} />
          <PortInput label={t('topology.fromPort')} placeholder="Te1/1/1" switchName={form.a} value={form.a_port} onChange={(v) => set({ a_port: v })} />
          <Select label={t('topology.to')} data={switches} searchable value={form.b || null} onChange={(v) => set({ b: v ?? '' })} />
          <PortInput label={t('topology.toPort')} placeholder="Te1/0/1" switchName={form.b} value={form.b_port} onChange={(v) => set({ b_port: v })} />
          <Select label={t('topology.type')} clearable value={form.type || null} onChange={(v) => set({ type: v ?? '' })}
            data={data.types.map((v) => ({ value: v, label: t(`topology.types.${v}`) }))} />
          <Select label={t('topology.speed')} clearable value={form.speed || null} onChange={(v) => set({ speed: v ?? '' })}
            data={data.speeds.map((v) => ({ value: String(v), label: `${v}G` }))} />
        </SimpleGrid>
        <TextInput label={t('topology.note')} value={form.note} onChange={(e) => set({ note: e.currentTarget.value })} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={!form.a || !form.b || !form.a_port.trim() || !form.b_port.trim()}
            onClick={() => save.mutate()}>{t('topology.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** A port field that offers the switch's ports as the monitoring source reads them: free ones first,
 *  each with its state, and the ones a link already uses with where that link goes. Typing any name
 *  still works, for a switch that can't be read. */
function PortInput({ label, placeholder, switchName, value, onChange }: {
  label: string; placeholder: string; switchName: string; value: string; onChange: (v: string) => void
}) {
  const { t } = useTranslation()
  const q = useQuery({
    queryKey: [...qk.topology, 'ports', switchName],
    queryFn: () => get<{ ports: SwitchPort[] }>(`/api/links/ports?switch=${encodeURIComponent(switchName)}`),
    enabled: !!switchName, staleTime: 30_000,
  })
  const ports = q.data?.ports ?? []
  const byName = new Map(ports.map((p) => [p.name, p]))
  const free = ports.filter((p) => !p.used_by).map((p) => p.name)
  const used = ports.filter((p) => p.used_by).map((p) => p.name)
  const data = [
    ...(free.length ? [{ group: t('topology.portsFree'), items: free }] : []),
    ...(used.length ? [{ group: t('topology.portsUsed'), items: used }] : []),
  ]
  return (
    <Autocomplete label={label} placeholder={placeholder} value={value} onChange={onChange} data={data} limit={200}
      maxDropdownHeight={280} description={switchName && q.isSuccess && !ports.length ? t('topology.portsUnread') : undefined}
      renderOption={({ option }) => {
        const p = byName.get(option.value)
        return (
          <Group gap={6} wrap="nowrap" justify="space-between" style={{ width: '100%' }}>
            <Text size="sm" ff="monospace">{option.value}</Text>
            <Text size="xs" c="dimmed">
              {p?.used_by ? t('topology.portUsedBy', { other: p.used_by }) : [t(`topology.state.${p?.state === 'up' || p?.state === 'down' ? p.state : 'unknown'}`), gbit(p?.speed_bps ?? null)].filter(Boolean).join(' · ')}
            </Text>
          </Group>
        )
      }} />
  )
}

function UplinkPanel({ uplink: u }: { uplink: TopologyUplink }) {
  const { t } = useTranslation()
  const tone = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }[u.status]
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{u.name}</Title>
        <Badge color={tone} variant="light">{t(`topology.uplinkStatus.${u.status}`)}</Badge>
      </Group>
      <Text size="sm" c="dimmed">{t('topology.uplink')}</Text>
      <SimpleGrid cols={2} spacing={4}>
        <Text size="sm" c="dimmed">{t('topology.uplinkPort')}</Text><Text size="sm" ff="monospace">{u.device} {u.port}</Text>
        <Text size="sm" c="dimmed">{t('topology.uplinkCapacity')}</Text><Text size="sm">{u.capacity_mbps ? `${u.capacity_mbps} Mbit/s` : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.uplinkUsed')}</Text><Text size="sm">{u.utilization != null ? `${Math.round(u.utilization * 100)} %` : '–'}</Text>
      </SimpleGrid>
      <Button size="compact-sm" variant="default" component="a" href="/services" mt={4} style={{ alignSelf: 'flex-start' }}>{t('topology.openServices')}</Button>
    </Stack>
  )
}

/** The floor plan's grid (styles/plan.css .fb-grid) under the diagram, in its units so it pans and
 *  zooms with it; lines stay 1px on screen. */
function TopologyGrid({ id, view, base, scale }: { id: string; view: ViewBox; base: ViewBox; scale: number }) {
  const w = 1 / (scale || 1)
  const x = Math.min(view.x, base.x), y = Math.min(view.y, base.y)
  const x2 = Math.max(view.x + view.w, base.x + base.w), y2 = Math.max(view.y + view.h, base.y + base.h)
  return (
    <g aria-hidden="true">
      <defs>
        <pattern id={id} width={100} height={100} patternUnits="userSpaceOnUse">
          <path className="grid-minor" strokeWidth={w} d="M20 0V100M40 0V100M60 0V100M80 0V100M0 20H100M0 40H100M0 60H100M0 80H100" />
          <path className="grid-major" strokeWidth={w} d="M0 0V100M0 0H100" />
        </pattern>
      </defs>
      <rect x={x} y={y} width={x2 - x} height={y2 - y} fill={`url(#${id})`} />
    </g>
  )
}
