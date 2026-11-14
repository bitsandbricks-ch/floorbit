import { Alert, Anchor, Drawer, Group, Loader, Paper, SegmentedControl, Select, Text, TextInput } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { SeatViewData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { Inspector, Legend } from './plan/Inspector'
import { type Filter, type View, around, findSeat, parseBox, seatCenter } from './plan/model'
import { SeatMap } from './plan/SeatMap'

const FILTERS: Filter[] = ['all', 'problems', 'offline', 'match', 'checked_in']

/** The floor plan's seats (issue #55): one state per seat that reads the same in every theme and
 *  for colour-blind eyes, three zoom levels, and one inspector for a seat. ``?screen=1`` for a kiosk. */
export default function FloorPlan() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const hall = params.get('hall') ?? ''
  const selected = params.get('seat')
  const screen = params.get('screen') === '1'
  const phone = useMediaQuery('(max-width: 48em)')
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: qk.plan(hall),
    queryFn: () => get<SeatViewData>(`/api/plan${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`),
    refetchInterval: 30_000,
  })
  const refresh = useCallback(() => { void qc.invalidateQueries({ queryKey: qk.planAll }) }, [qc])
  useLiveEvent('stats.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('incident.changed', refresh)
  const data = q.data
  const [saved, setSaved] = useState<{ box: string; view: View } | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const box = data?.drawing?.box
  // A new hall (or a changed drawing) starts fitted, or on the seat in the link it was opened with.
  const [linked] = useState(selected)
  const start = (() => {
    if (!box || !data?.drawing) return null
    const fit = parseBox(box)
    const at = linked ? seatCenter(data.drawing, linked) : null
    return at ? around(at, Math.max(fit.w / 2, 480), fit) : fit
  })()
  const view = saved && saved.box === box ? saved.view : start
  const setView = useCallback((v: View) => { if (box) setSaved({ box, view: v }) }, [box])

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const go = (e: React.FormEvent) => {
    e.preventDefault()
    if (!data?.drawing || !view) return
    const seat = findSeat(search, data.seats)
    const at = seat && seatCenter(data.drawing, seat)
    if (!seat || !at) return
    set('seat', seat)
    setView(around(at, Math.max(parseBox(data.drawing.box).w / 2, 480), view))
  }
  const notFound = search.trim() !== '' && data ? !findSeat(search, data.seats) : false
  const total = data ? Object.keys(data.seats).length : 0
  const online = data ? Object.values(data.seats).filter((s) => s.state === 'online').length : 0
  const problems = data ? Object.values(data.seats).filter((s) => s.problems).length : 0
  const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })

  const map = data?.drawing && view && (
    <SeatMap data={data} view={view} setView={setView} filter={filter} selected={selected}
      onSelect={(s) => { if (!screen) set('seat', s === selected ? null : s) }} />
  )
  const summary = data && (
    <Group gap="lg" className="fb-plan-summary" wrap="wrap">
      <Text><b>{online}</b> / {total} {t('plan.online')}</Text>
      <Text c={problems ? 'down' : 'dimmed'}><b>{problems}</b> {t('plan.withProblems')}</Text>
      {data.last_read && <Text c="dimmed" size="sm">{t('plan.lastRead', { time: clock(data.last_read) })}</Text>}
    </Group>
  )

  if (screen) {
    return (
      <main className="fb-plan-screen">
        {summary}
        {map}
        {data && <Legend checkin={data.checkin} />}
      </main>
    )
  }

  const inspector = selected && <Inspector key={selected} seat={selected} onClose={() => set('seat', null)} />
  return (
    <Layout title={t('plan.title')} back={{ href: '/', label: t('plan.editor') }}>
      {q.isPending && <Loader aria-label={t('common.loading')} />}
      {q.error && <Alert color="down" role="alert">{t('common.error', { message: q.error.message })}</Alert>}
      {data && (
        <>
          <Group justify="space-between" mb="sm" gap="sm" wrap="wrap">
            {summary}
            <Group gap="xs" wrap="wrap">
              {data.halls.length > 1 && (
                <Select aria-label={t('plan.hall')} w={180} allowDeselect={false} value={data.hall}
                  data={data.halls.map((h) => ({ value: h.id, label: h.name }))}
                  onChange={(v) => { const next = new URLSearchParams(); if (v) next.set('hall', v); setParams(next) }} />
              )}
              <form onSubmit={go} role="search">
                <TextInput aria-label={t('plan.find')} placeholder={t('plan.findHint')} w={160} value={search}
                  leftSection={<IconSearch size={14} />} error={notFound ? t('plan.notFound') : undefined}
                  onChange={(e) => setSearch(e.currentTarget.value)} />
              </form>
            </Group>
          </Group>
          {!data.monitoring && <Alert color="warn" mb="sm">{t('plan.noMonitoring')}</Alert>}
          <SegmentedControl mb="sm" size="xs" value={filter} onChange={(v) => setFilter(v as Filter)} aria-label={t('plan.show')}
            data={FILTERS.filter((f) => data.checkin || f !== 'checked_in').map((f) => ({ value: f, label: t(`plan.filter.${f}`) }))} />
          {!data.drawing && (
            <Paper withBorder radius="lg" p="lg"><Text>{t('plan.empty')}</Text><Anchor href="/" mt="xs" display="inline-block">{t('plan.emptyLink')}</Anchor></Paper>
          )}
          <div className={`fb-plan-layout${selected && !phone ? ' with-inspector' : ''}`}>
            {map}
            {selected && !phone && <Paper withBorder radius="lg" p="md">{inspector}</Paper>}
          </div>
          <Legend checkin={data.checkin} />
          <Text size="sm" c="dimmed" mt="xs">{t('plan.help')}</Text>
          {phone && (
            <Drawer opened={!!selected} onClose={() => set('seat', null)} position="bottom" size="55%" withCloseButton={false}
              title={null} aria-label={selected ?? ''}>
              {inspector}
            </Drawer>
          )}
        </>
      )}
    </Layout>
  )
}
