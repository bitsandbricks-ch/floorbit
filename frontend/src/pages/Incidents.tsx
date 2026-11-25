import { Badge, Button, Group, Kbd, SegmentedControl, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { useDisclosure, useHotkeys, useMediaQuery } from '@mantine/hooks'
import { IconDownload, IconFilter, IconHandGrab, IconPlus, IconQrcode } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useFeature, useIncidentPeople, useIncidents, useMe } from '@/api/queries'
import type { CrewMember, Incident, IncidentStatus } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { useNowSeconds } from '@/components/useNowSeconds'
import { matchesFilter } from './incidents/filter'
import { MyJobs } from './incidents/MyJobs'
import { IncidentCard, type IncidentChange } from './incidents/IncidentCard'
import { IncidentTable } from './incidents/IncidentTable'
import { NewIncident, type IncidentDraft } from './incidents/NewIncident'
import { isSnoozed, nextToTake, openOrder } from './incidents/waiting'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'

const COLUMNS: IncidentStatus[] = ['open', 'assigned', 'fixed']
const FIXED_SHOWN = 20

/** The incident board: open, being worked, fixed. Seat reports from the QR helpdesk land here too. */
export default function Incidents() {
  const { t } = useTranslation()
  const helpdeskOn = useFeature('helpdesk')
  const client = useQueryClient()
  const board = useIncidents()
  const people = useIncidentPeople()
  const me = useMe()
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches') })
  const [mineOnly, setMineOnly] = useState(false)
  const dispatchOn = useFeature('dispatch')
  const now = useNowSeconds()
  // The filter lives in the address, so a link can open the board filtered (issue #210).
  // The box keeps its own state: the address updates a moment later, and typing fast against it lost letters (issue #226).
  const [params, setParams] = useSearchParams()
  // "Assigned to me" in the address, so Discord's /jobs can link straight to it (issue #887).
  const assignedToMe = params.get('mine') === '1'
  const setAssignedToMe = (on: boolean) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    if (on) next.set('mine', '1'); else next.delete('mine')
    return next
  }, { replace: true })
  // Board or table (issue #887), in the address so a link or a reload keeps it.
  const view = params.get('view') === 'table' ? 'table' : 'board'
  const setView = (v: string) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    if (v === 'table') next.set('view', 'table'); else next.delete('view')
    return next
  }, { replace: true })
  const [filter, setFilterText] = useState(() => params.get('q') ?? '')
  const setFilter = (v: string) => {
    setFilterText(v)
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (v) next.set('q', v)
      else next.delete('q')
      return next
    }, { replace: true })
  }
  // "/" jumps to the filter, as on the Seats page; with Shift for Swiss and German keyboards (issue #226).
  const filterBox = useRef<HTMLInputElement>(null)
  const keyboard = useMediaQuery('(hover: hover) and (pointer: fine)')
  const toFilter = () => { filterBox.current?.focus(); filterBox.current?.select() }
  useHotkeys([['/', toFilter], ['shift+/', toFilter]])
  const [formOpen, form] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const crew = useQuery({
    queryKey: qk.crew, queryFn: () => get<{ crew: CrewMember[]; auto?: boolean }>('/api/dispatch/crew'),
    enabled: !!board.data?.can_assign_any, refetchInterval: 30_000,
  })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: qk.incidents })
    void client.invalidateQueries({ queryKey: qk.crew })
  }
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('dispatch.changed', refresh)
  const send = useMutation({
    mutationFn: (id: string) => post<{ display_name: string }>(`/api/incidents/${id}/dispatch`),
    onSuccess: (r) => {
      refresh()
      setMessage({ ok: true, text: t('incidents.sentTo', { name: r.display_name }) })
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  // With nobody on duty the button could only fail, so the cards don't offer it.
  const anyoneOnDuty = !!crew.data?.crew.length

  // New incidents go to the nearest free tech by themselves while this is on (issue #358).
  const auto = useMutation({
    mutationFn: (on: boolean) => put<{ auto: boolean }>('/api/dispatch/auto', { on }),
    onSuccess: refresh,
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  const create = useMutation({
    mutationFn: (d: IncidentDraft) => post<Incident>('/api/incidents', d),
    onSuccess: () => {
      refresh()
      form.close()
      setMessage({ ok: true, text: t('incidents.filed') })
    },
    onError: (e) => setFormError(e.message),
  })
  const change = useMutation({
    mutationFn: (v: { id: string; change: IncidentChange; next?: boolean }) => patch<Incident>(`/api/incidents/${v.id}`, v.change),
    onSuccess: (r, v) => {
      if (v.next) setMessage({ ok: true, text: t('incidents.tookNext', { title: r.title }) })
      refresh()
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  const teamNames = Object.fromEntries((board.data?.teams ?? []).map((x) => [x.id, x.name]))
  const next = nextToTake(board.data?.incidents ?? [], now)
  const username = me.data?.user?.username
  const takeNext = () => {
    if (next && username && !change.isPending) change.mutate({ id: next.id, change: { status: 'assigned', assignee: username }, next: true })
  }
  // "n" takes the next one, like "/" jumps to the filter (issue #316); typing in a field doesn't count.
  useHotkeys([['n', takeNext]])
  const items = (board.data?.incidents ?? []).filter((i) => (!mineOnly || i.can_work)
    && (!assignedToMe || (!!username && i.assignee === username)) && matchesFilter(i, filter, teamNames))
  return (
    <Layout title={t('incidents.title')} back={{ href: '/', label: t('common.floorPlan') }}
      count={(board.data?.incidents ?? []).filter((i) => i.status === 'open' && !isSnoozed(i, now)).length}>
      <PageHead
        title={t('incidents.title')}
        desc={t('incidents.intro')}
        actions={
          <>
            {/* The handover is a Helpdesk tab (issue #892); My jobs is part of this board (issue #887). */}
            {board.data?.can_assign_any && helpdeskOn && (
              <Button variant="default" component="a" href="/incidents/qr" leftSection={<IconQrcode size={16} />}>
                {t('incidents.qrCodes')}
              </Button>
            )}
            <Button variant="default" component="a" href={`/api/incidents.csv?tz=${new Date().getTimezoneOffset()}`}
              leftSection={<IconDownload size={16} />}>
              {t('incidents.csv')}
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => { setFormError(null); form.open() }} disabled={!board.data}>
              {t('incidents.new')}
            </Button>
          </>
        }
      />
      {dispatchOn && me.data?.user && <MyJobs />}
      <Group justify="space-between" mb="sm">
        <Group gap="md">
          <SegmentedControl size="sm" aria-label={t('incidentTable.view')} value={view} onChange={setView}
            data={[{ value: 'board', label: t('incidentTable.board') }, { value: 'table', label: t('incidentTable.table') }]} />
          <TextInput ref={filterBox} aria-label={t('incidents.filter')} aria-keyshortcuts="/" placeholder={t('incidents.filterHint')} w={300} value={filter}
            leftSection={<IconFilter size={14} />} rightSection={keyboard ? <Kbd size="xs">/</Kbd> : undefined}
            onChange={(e) => setFilter(e.currentTarget.value)} />
          <Switch label={t('incidents.assignedToMe')} checked={assignedToMe} onChange={(e) => setAssignedToMe(e.currentTarget.checked)} />
          <Switch label={t('incidents.mineOnly')} checked={mineOnly} onChange={(e) => setMineOnly(e.currentTarget.checked)} />
          {me.data?.user && (
            <Button variant="default" leftSection={<IconHandGrab size={16} />} disabled={!next} loading={change.isPending && change.variables?.next}
              title={next ? next.title : t('incidents.nothingNext')} aria-keyshortcuts="n"
              rightSection={keyboard ? <Kbd size="xs" aria-hidden>n</Kbd> : undefined} onClick={takeNext}>
              {t('incidents.takeNext')}
            </Button>
          )}
        </Group>
        <Text size="sm" role="status" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
          {message?.text}
        </Text>
      </Group>
      {crew.data && (
        <Group gap={6} mb="sm" aria-label={t('incidents.crew')} role="group">
          <Text size="sm" fw={600}>{t('incidents.crew')}:</Text>
          {crew.data.crew.length === 0 && <Text size="sm" c="dimmed">{t('incidents.crewNone')}</Text>}
          {crew.data.crew.map((c) => (
            // A tech's badge filters the board to what they are on (issue #350); again to clear.
            <Badge key={c.username} component="button" type="button" variant={filter === `with:${c.username}` ? 'filled' : 'light'}
              color={c.jobs ? 'warn' : 'up'} tt="none" style={{ cursor: 'pointer' }}
              aria-pressed={filter === `with:${c.username}`}
              onClick={() => setFilter(filter === `with:${c.username}` ? '' : `with:${c.username}`)}>
              {c.display_name}{c.at ? ` · ${c.at}` : ''} · {c.jobs ? t('incidents.crewJobs', { count: c.jobs }) : t('incidents.crewFree')}{c.done ? ` · ${t('incidents.crewDone', { count: c.done })}` : ''}
            </Badge>
          ))}
          <Switch ml="auto" size="sm" label={t('incidents.autoDispatch')} checked={!!crew.data.auto} disabled={auto.isPending}
            onChange={(e) => auto.mutate(e.currentTarget.checked)} />
        </Group>
      )}
      <ErrorBanner error={board.error} mb="md" onRetry={() => void board.refetch()} />
      {board.isPending ? (
        <LoadingState rows={3} />
      ) : view === 'table' ? (
        board.data && <IncidentTable items={items} board={board.data} />
      ) : (
        board.data && (
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
            {COLUMNS.map((status) => {
              const column = items.filter((i) => i.status === status)
              const shown = status === 'fixed' ? column.slice(0, FIXED_SHOWN) : status === 'open' ? openOrder(column, now) : column
              return (
                <Stack key={status} gap="sm" aria-label={t(`incidents.status.${status}`)} role="region">
                  <Group gap="xs">
                    <Title order={3} size="h4">{t(`incidents.status.${status}`)}</Title>
                    <Badge variant="light" color={status === 'open' && column.length ? 'down' : 'gray'}>{column.length}</Badge>
                  </Group>
                  {!column.length && <Text size="sm" c="dimmed">{filter ? t('incidents.noMatch') : t(`incidents.empty.${status}`)}</Text>}
                  {shown.map((i) => (
                    <IncidentCard key={i.id} incident={i} board={board.data} people={people.data} me={me.data?.user?.username}
                      busy={(change.isPending && change.variables?.id === i.id) || (send.isPending && send.variables === i.id)}
                      onChange={(c) => change.mutate({ id: i.id, change: c })}
                      onDispatch={anyoneOnDuty ? () => send.mutate(i.id) : undefined} />
                  ))}
                </Stack>
              )
            })}
          </SimpleGrid>
        )
      )}
      {board.data && formOpen && (
        <NewIncident board={board.data} switches={switches.data ?? []} opened={formOpen} busy={create.isPending} error={formError}
          onClose={form.close} onSave={(d) => create.mutate(d)} />
      )}
    </Layout>
  )
}
