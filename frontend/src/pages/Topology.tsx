import {
  ActionIcon, Alert, Autocomplete, Badge, Box, Button, Drawer, Group, Menu, Modal, Paper, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { useElementSize, useMediaQuery } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconFocusCentered, IconLine, IconPhoto, IconVectorBezier2, IconZoomIn, IconZoomOut } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { LinkSuggestion, SwitchLink, SwitchPort, Topology as TopologyData, TopologyNode, TopologyUplink } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { download, standaloneSvg, svgToPng } from './plan/exportImage'
import { type Box as ViewBox, bounds, toDiagram, zoomAt } from './topology/camera'
import { NODE_H, NODE_W, type Placed, arranged, gbit, layout, placeUplinks } from './topology/layout'

const COLOR: Record<string, string> = {
  cat5e: 'var(--mantine-color-blue-6)', cat6: 'var(--mantine-color-blue-6)', cat6a: 'var(--mantine-color-blue-6)',
  'fiber-sm': 'var(--mantine-color-yellow-6)', 'fiber-mm': 'var(--mantine-color-cyan-6)', dac: 'var(--mantine-color-violet-6)',
  '': 'var(--mantine-color-gray-5)',
}
const WIDTH: Record<number, number> = { 1: 1.5, 10: 2.5, 25: 3, 40: 4, 100: 5 }
const READABLE = 0.75 // the smallest scale the opening view shows names at


type Picked = { kind: 'link'; id: string } | { kind: 'node'; name: string } | { kind: 'uplink'; id: string } | null

const UPLINK_COLOR = { up: 'var(--mantine-color-green-6)', warn: 'var(--mantine-color-orange-6)', down: 'var(--mantine-color-red-6)', unknown: 'var(--mantine-color-gray-5)' } as const
type Draft = Partial<SwitchLink> & { id?: string }

/** The network's links between switches (issue #468): type and speed, down or slower than planned,
 *  and what LLDP sees that no link explains yet. The diagram pans and zooms, the crew drags its boxes
 *  where they belong (kept for everyone), draws a link by picking two boxes, and it saves as PNG or SVG. */
export default function Topology() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const phone = useMediaQuery('(max-width: 48em)')
  const q = useQuery({ queryKey: qk.topology, queryFn: () => get<TopologyData>('/api/links'), refetchInterval: 30_000 })
  const [picked, setPicked] = useState<Picked>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [wire, setWire] = useState<{ a?: string } | null>(null)
  const [cam, setCam] = useState<ViewBox | null>(null) // null: the opening view (see `start`)
  const { ref: paneRef, width: paneWidth } = useElementSize()
  const [drag, setDrag] = useState<{ key: string; x: number; y: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const gesture = useRef<{ kind: 'pan' | 'node'; key?: string; sx: number; sy: number; ox: number; oy: number; cam: ViewBox; moved: boolean } | null>(null)
  const moved = useRef(false) // the last press dragged something: its click isn't a pick
  const data = q.data
  const auto = useMemo(() => (data ? layout(data.nodes, data.links) : null), [data])
  const placed = useMemo(() => (auto ? arranged(auto, data?.layout) : null), [auto, data?.layout])
  const lines = useMemo(() => (placed && data ? placeUplinks(placed, data.uplinks ?? []) : null), [placed, data])
  // where a box is drawn: being dragged, or where the layout puts it
  const spot = useCallback((p: Placed) => (drag && drag.key === p.node.name.toLowerCase() ? { x: drag.x, y: drag.y } : { x: p.x, y: p.y }), [drag])
  const base = useMemo<ViewBox | null>(() => {
    if (!placed || !lines) return null
    const boxes = [...placed.placed.values()].map((p) => ({ ...spot(p), w: NODE_W, h: NODE_H })).map((b) => ({ ...b, x: b.x + lines.dx, y: b.y + lines.dy }))
    return bounds([...boxes, ...lines.boxes.map((b) => ({ x: b.x, y: b.y, w: NODE_W, h: NODE_H }))])
  }, [placed, lines, spot])
  // Fitted, 26 boxes in a narrow pane are too small to read (#1050): open at a readable size from the
  // top of the network instead, and leave the whole picture to the fit button.
  const start = useMemo<ViewBox | null>(() => {
    if (!base || !paneWidth) return base
    if (paneWidth / base.w >= READABLE) return base
    // As wide as the pane shows at READABLE, and as tall as the picture, up to most of the screen.
    const w = paneWidth / READABLE, h = Math.min(base.h, (window.innerHeight * 0.75) / READABLE)
    return { x: base.x + (base.w - w) / 2, y: base.y, w, h }
  }, [base, paneWidth])
  const view = cam ?? start
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
  useEffect(() => {
    if (!wire) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setWire(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [wire])

  const zoomBy = (factor: number) => { if (view && base) setCam(zoomAt(view, base, factor, { x: view.x + view.w / 2, y: view.y + view.h / 2 })) }
  const pickNode = (name: string) => {
    if (!wire) { setPicked({ kind: 'node', name }); return }
    if (!wire.a) { setWire({ a: name }); return }
    if (wire.a !== name) { setDraft({ a: wire.a, b: name }); setWire(null) }
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
    // Every box's place goes with it, so the picture stays as it is when one box is moved.
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

  const panel = uplink ? <UplinkPanel uplink={uplink} />
    : link ? <LinkPanel link={link} canEdit={canEdit} onEdit={() => setDraft(link)} onGone={() => setPicked(null)} />
    : node ? <NodePanel name={node.name} role={node.role} status={node.status} links={data!.links.filter((l) => l.a === node.name || l.b === node.name)}
      onPick={(id) => setPicked({ kind: 'link', id })} />
      : null

  return (
    <Layout title={t('topology.title')}>
      <PageHead title={t('topology.title')} desc={t('topology.intro')}
        actions={canEdit && <Button onClick={() => setDraft({})}>{t('topology.add')}</Button>} />
      <Stack gap="md">
        {q.error && <Alert color="down" role="alert">{q.error.message}</Alert>}
        {problems.length > 0 && (
          <Alert color={problems.some((l) => l.issue === 'down') ? 'down' : 'warn'} title={t('topology.problems', { count: problems.length })}>
            <Stack gap={2}>
              {problems.map((l) => (
                <Text key={l.id} size="sm" component="button" type="button" className="fb-text-button"
                  onClick={() => setPicked({ kind: 'link', id: l.id })}>
                  {l.issue
                    ? t(`topology.issue.${l.issue}`, { a: `${l.a} ${l.a_port}`, b: `${l.b} ${l.b_port}`, planned: `${l.speed}G`, actual: gbit(l.speed_bps) })
                    : t('topology.issue.miswired', { a: `${l.a} ${l.a_port}`, b: `${l.b} ${l.b_port}`, ...seenAt(l) })}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}
        {data && data.links.length === 0 && (
          <Paper withBorder radius="lg" p="md"><Text c="dimmed">{t(canEdit ? 'topology.emptyEdit' : 'topology.empty')}</Text></Paper>
        )}
        {data && placed && lines && view && base && data.links.length > 0 && (
          <Box style={{ display: 'grid', gap: 16, gridTemplateColumns: phone || !panel ? '1fr' : 'minmax(0, 1fr) 300px' }}>
            <Paper withBorder radius="lg" p="sm" style={{ position: 'relative', overflow: 'hidden' }}>
              <div ref={paneRef} aria-hidden="true" style={{ height: 0 }} />
              <Group gap={6} mb={6} wrap="wrap">
                <ActionIcon.Group>
                  <ActionIcon variant="default" aria-label={t('topology.zoomIn')} title={t('topology.zoomIn')} onClick={() => zoomBy(1.4)}><IconZoomIn size={16} aria-hidden="true" /></ActionIcon>
                  <ActionIcon variant="default" aria-label={t('topology.zoomOut')} title={t('topology.zoomOut')} onClick={() => zoomBy(1 / 1.4)}><IconZoomOut size={16} aria-hidden="true" /></ActionIcon>
                  <ActionIcon variant="default" aria-label={t('topology.fit')} title={t('topology.fit')} onClick={() => setCam(base)}><IconFocusCentered size={16} aria-hidden="true" /></ActionIcon>
                </ActionIcon.Group>
                {canEdit && (
                  <Button size="compact-sm" variant={wire ? 'filled' : 'default'} leftSection={<IconLine size={14} aria-hidden="true" />}
                    onClick={() => setWire(wire ? null : {})} aria-pressed={!!wire}>{t(wire ? 'topology.drawCancel' : 'topology.draw')}</Button>
                )}
                <Box style={{ flex: 1 }} />
                {canEdit && arrangedByCrew && (
                  <ConfirmButton size="compact-sm" variant="subtle" label={t('topology.arrange')} question={t('topology.arrangeQuestion')}
                    onConfirm={() => resetLayout.mutate()} />
                )}
                <Menu position="bottom-end" withinPortal>
                  <Menu.Target>
                    <Button size="compact-sm" variant="default" leftSection={<IconDownload size={14} aria-hidden="true" />}>{t('topology.export')}</Button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item leftSection={<IconPhoto size={14} />} onClick={() => void exportAs('png')}>{t('topology.exportPng')}</Menu.Item>
                    <Menu.Item leftSection={<IconVectorBezier2 size={14} />} onClick={() => void exportAs('svg')}>{t('topology.exportSvg')}</Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              </Group>
              {wire && (
                <Text size="sm" mb={6} role="status">{wire.a ? t('topology.drawSecond', { a: wire.a }) : t('topology.drawFirst')}</Text>
              )}
              {saveLayout.error && <Alert color="down" role="alert" mb={6}>{saveLayout.error.message}</Alert>}
              <svg ref={svgRef} role="img" aria-label={t('topology.diagram', { count: data.links.length })}
                viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} className="fb-topology"
                onPointerDown={(e) => down(e)} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { gesture.current = null; setDrag(null) }}
                style={{ display: 'block', width: '100%', height: 'auto', maxHeight: '75vh', touchAction: 'none', cursor: wire ? 'crosshair' : 'grab', userSelect: 'none' }}>
                {lines.boxes.map(({ uplink: u, x, y, to }) => {
                  const chosen = picked?.kind === 'uplink' && picked.id === u.id
                  const toAt = spot(to)
                  return (
                    <g key={u.id} className="fb-uplink" data-status={u.status} onClick={() => { if (!clickedAfterMove()) setPicked({ kind: 'uplink', id: u.id }) }} style={{ cursor: 'pointer' }}>
                      <title>{`${u.name}: ${u.device} ${u.port} · ${t(`topology.uplinkStatus.${u.status}`)}`}</title>
                      <line x1={x + NODE_W / 2} y1={y + NODE_H} x2={toAt.x + lines.dx + NODE_W / 2} y2={toAt.y + lines.dy}
                        stroke={UPLINK_COLOR[u.status]} strokeWidth={3} strokeDasharray={u.status === 'down' ? '6 4' : undefined} strokeLinecap="round" />
                      {/* A cloud-ish pill, so the internet doesn't read as one more switch. */}
                      <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={NODE_H / 2} fill="var(--mantine-color-body)"
                        stroke={chosen ? 'var(--mantine-primary-color-filled)' : UPLINK_COLOR[u.status]} strokeWidth={chosen ? 2.5 : 1.8} />
                      <text x={x + NODE_W / 2} y={y + NODE_H / 2} dominantBaseline="central" textAnchor="middle" fontSize={12}
                        fill="var(--mantine-color-text)" fontWeight={600}>
                        {u.name.length > 15 ? `${u.name.slice(0, 14)}…` : u.name}
                      </text>
                    </g>
                  )
                })}
                <g transform={`translate(${lines.dx} ${lines.dy})`}>
                {data.links.map((l) => {
                  const pa = placed.placed.get(l.a.toLowerCase()), pb = placed.placed.get(l.b.toLowerCase())
                  if (!pa || !pb) return null
                  const a = spot(pa), b = spot(pb)
                  // Out of the bottom of the upper box into the top of the lower one; side by side, middle to middle.
                  const [top, bottom] = a.y <= b.y ? [a, b] : [b, a]
                  const level = Math.abs(top.y - bottom.y) < NODE_H
                  const x1 = top.x + NODE_W / 2, y1 = level ? top.y + NODE_H / 2 : top.y + NODE_H
                  const x2 = bottom.x + NODE_W / 2, y2 = level ? bottom.y + NODE_H / 2 : bottom.y
                  const color = l.issue === 'down' ? 'var(--mantine-color-red-6)' : l.issue === 'slow' ? 'var(--mantine-color-orange-6)' : COLOR[l.type]
                  const chosen = picked?.kind === 'link' && picked.id === l.id
                  return (
                    <g key={l.id} onClick={() => { if (!clickedAfterMove() && !wire) setPicked({ kind: 'link', id: l.id }) }} style={{ cursor: 'pointer' }}>
                      <title>{`${l.a} ${l.a_port} – ${l.b} ${l.b_port}${l.speed ? ` · ${l.speed}G` : ''}`}</title>
                      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={14} />
                      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={(WIDTH[l.speed ?? 0] ?? 1.5) + (chosen ? 2 : 0)}
                        strokeDasharray={l.issue === 'down' ? '6 4' : l.type === '' ? '2 3' : undefined} strokeLinecap="round" />
                    </g>
                  )
                })}
                {[...placed.placed.entries()].map(([key, p]) => {
                  const chosen = (picked?.kind === 'node' && picked.name === p.node.name) || wire?.a === p.node.name
                  const at = spot(p)
                  return (
                    <g key={p.node.id} transform={`translate(${at.x} ${at.y})`} data-node={p.node.name}
                      onPointerDown={(e) => { e.stopPropagation(); if (canEdit && !wire) down(e as unknown as React.PointerEvent<SVGSVGElement>, key); else { gesture.current = null; moved.current = false } }}
                      onClick={() => { if (!clickedAfterMove()) pickNode(p.node.name) }}
                      style={{ cursor: wire ? 'crosshair' : canEdit ? 'move' : 'pointer' }}>
                      <title>{`${p.node.name}: ${t(`topology.status.${p.node.status}`)}`}</title>
                      {/* A box that is down: red, dashed and struck through, so it doesn't rely on colour. */}
                      <rect width={NODE_W} height={NODE_H} rx={8} fill={p.node.status === 'offline' ? 'var(--mantine-color-red-light)' : 'var(--mantine-color-body)'}
                        stroke={chosen ? 'var(--mantine-primary-color-filled)' : p.node.status === 'offline' ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-default-border)'}
                        strokeWidth={chosen || p.node.status === 'offline' ? 2.5 : 1.2} strokeDasharray={p.node.status === 'offline' ? '6 4' : undefined}
                        data-status={p.node.status} />
                      <circle cx={10} cy={10} r={4} fill={p.node.status === 'online' ? 'var(--mantine-color-green-6)' : p.node.status === 'offline' ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-gray-5)'} />
                      <text x={NODE_W / 2} y={NODE_H / 2} dominantBaseline="central" textAnchor="middle" fontSize={13}
                        fill="var(--mantine-color-text)" fontWeight={p.node.role === 'switch' ? 400 : 600}>
                        {p.node.name.length > 15 ? `${p.node.name.slice(0, 14)}…` : p.node.name}
                      </text>
                    </g>
                  )
                })}
                </g>
              </svg>
              <Legend links={data.links} />
              <Text size="xs" c="dimmed" mt={4}>{t(canEdit ? 'topology.pickHintEdit' : 'topology.pickHint')} {t(canEdit ? 'topology.howEdit' : 'topology.how')}</Text>
            </Paper>
            {phone
              ? <Drawer opened={!!panel} onClose={() => setPicked(null)} position="bottom" size="55%"
                aria-label={link ? t('topology.link') : node?.name}>{panel}</Drawer>
              : panel && <Paper withBorder radius="lg" p="md" style={{ alignSelf: 'start' }}>{panel}</Paper>}
          </Box>
        )}
        {placed && placed.loose.length > 0 && data!.links.length > 0 && (
          <Text size="sm" c="dimmed">{t('topology.loose', { names: placed.loose.map((n) => n.name).join(', ') })}</Text>
        )}
        {data && data.suggestions.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Title order={3} size="h5" mb={4}>{t('topology.suggestions', { count: data.suggestions.length })}</Title>
            <Text size="sm" c="dimmed" mb="sm">{t('topology.suggestionsHint')}</Text>
            <Stack gap={6}>
              {data.suggestions.map((s) => (
                <Group key={`${s.a}${s.a_port}${s.b}${s.b_port}`} justify="space-between" wrap="nowrap" gap="xs">
                  <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>
                    {s.a} {s.a_port} – {s.b} {s.b_port}{s.protocol ? ` (${s.protocol.toUpperCase()})` : ''}
                  </Text>
                  {canEdit && <Button size="compact-sm" variant="default" onClick={() => setDraft(fromSuggestion(s))}>{t('topology.addThis')}</Button>}
                </Group>
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
      {draft && data && <LinkModal draft={draft} data={data} onClose={() => setDraft(null)} />}
    </Layout>
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
  const all: [boolean, string, string, string?][] = [
    [has((l) => l.type.startsWith('cat')), t('topology.media.copper'), COLOR.cat6],
    [has((l) => l.type === 'fiber-sm'), t('topology.types.fiber-sm'), COLOR['fiber-sm']],
    [has((l) => l.type === 'fiber-mm'), t('topology.types.fiber-mm'), COLOR['fiber-mm']],
    [has((l) => l.type === 'dac'), t('topology.types.dac'), COLOR.dac],
    [has((l) => l.issue === 'slow'), t('topology.slow'), 'var(--mantine-color-orange-6)'],
    [has((l) => l.issue === 'down'), t('topology.down'), 'var(--mantine-color-red-6)', '6 4'],
  ]
  const items = all.filter(([shown]) => shown).map(([, ...rest]) => rest as [string, string, string?])
  const speeds = new Set(links.map((l) => l.speed).filter(Boolean)).size
  return (
    <Group gap="md" mt="xs" px={4}>
      {items.map(([label, color, dash]) => (
        <Group key={label} gap={6} wrap="nowrap">
          <svg width={24} height={8} aria-hidden="true"><line x1={1} y1={4} x2={23} y2={4} stroke={color} strokeWidth={3} strokeDasharray={dash} /></svg>
          <Text size="xs" c="dimmed">{label}</Text>
        </Group>
      ))}
      {speeds > 1 && <Text size="xs" c="dimmed">{t('topology.thicker')}</Text>}
    </Group>
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
        <Badge color={status === 'online' ? 'up' : status === 'offline' ? 'down' : 'gray'} variant="light">{t(`topology.status.${status}`)}</Badge>
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
