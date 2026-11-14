import { Alert, Badge, Button, Group, Kbd, Loader, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { useDisclosure, useHotkeys, useMediaQuery } from '@mantine/hooks'
import { IconArrowsExchange, IconBook, IconBox, IconFilter, IconListCheck, IconPlus, IconQrcode } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useFeature, useIncidentPeople, useIncidents, useMe } from '@/api/queries'
import type { CrewMember, Incident, IncidentStatus } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { matchesFilter } from './incidents/filter'
import { IncidentCard, type IncidentChange } from './incidents/IncidentCard'
import { NewIncident, type IncidentDraft } from './incidents/NewIncident'

const COLUMNS: IncidentStatus[] = ['open', 'assigned', 'fixed']
const FIXED_SHOWN = 20

/** The incident board: open, being worked, fixed. Seat reports from the QR helpdesk land here too. */
export default function Incidents() {
  const { t } = useTranslation()
  const dispatchOn = useFeature('dispatch')
  const handoverOn = useFeature('handover')
  const gearOn = useFeature('gear')
  const helpdeskOn = useFeature('helpdesk')
  const runbooksOn = useFeature('runbooks')
  const client = useQueryClient()
  const board = useIncidents()
  const people = useIncidentPeople()
  const me = useMe()
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches') })
  const [mineOnly, setMineOnly] = useState(false)
  // The filter lives in the address, so a link can open the board filtered (issue #210).
  // The box keeps its own state: the address updates a moment later, and typing fast against it lost letters (issue #226).
  const [params, setParams] = useSearchParams()
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
    queryKey: qk.crew, queryFn: () => get<{ crew: CrewMember[] }>('/api/dispatch/crew'),
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
    mutationFn: (v: { id: string; change: IncidentChange }) => patch<Incident>(`/api/incidents/${v.id}`, v.change),
    onSuccess: refresh,
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  const teamNames = Object.fromEntries((board.data?.teams ?? []).map((x) => [x.id, x.name]))
  const items = (board.data?.incidents ?? []).filter((i) => (!mineOnly || i.can_work) && matchesFilter(i, filter, teamNames))
  return (
    <Layout title={t('incidents.title')} back={{ href: '/', label: t('common.floorPlan') }}
      count={(board.data?.incidents ?? []).filter((i) => i.status === 'open').length}>
      <PageHead
        title={t('incidents.title')}
        desc={t('incidents.intro')}
        actions={
          <>
            {dispatchOn && (
              <Button variant="default" component="a" href="/jobs" leftSection={<IconListCheck size={16} />}>
                {t('incidents.myJobs')}
              </Button>
            )}
            {handoverOn && (
              <Button variant="default" component="a" href="/handover" leftSection={<IconArrowsExchange size={16} />}>
                {t('incidents.handover')}
              </Button>
            )}
            {runbooksOn && (
              <Button variant="default" component="a" href="/runbooks" leftSection={<IconBook size={16} />}>
                {t('incidents.runbooks')}
              </Button>
            )}
            {gearOn && (
              <Button variant="default" component="a" href="/gear" leftSection={<IconBox size={16} />}>
                {t('incidents.gear')}
              </Button>
            )}
            {board.data?.can_assign_any && helpdeskOn && (
              <Button variant="default" component="a" href="/incidents/qr" leftSection={<IconQrcode size={16} />}>
                {t('incidents.qrCodes')}
              </Button>
            )}
            <Button leftSection={<IconPlus size={16} />} onClick={() => { setFormError(null); form.open() }} disabled={!board.data}>
              {t('incidents.new')}
            </Button>
          </>
        }
      />
      <Group justify="space-between" mb="sm">
        <Group gap="md">
          <TextInput ref={filterBox} aria-label={t('incidents.filter')} aria-keyshortcuts="/" placeholder={t('incidents.filterHint')} w={240} value={filter}
            leftSection={<IconFilter size={14} />} rightSection={keyboard ? <Kbd size="xs">/</Kbd> : undefined}
            onChange={(e) => setFilter(e.currentTarget.value)} />
          <Switch label={t('incidents.mineOnly')} checked={mineOnly} onChange={(e) => setMineOnly(e.currentTarget.checked)} />
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
            <Badge key={c.username} variant="light" color={c.jobs ? 'warn' : 'up'} tt="none">
              {c.display_name}{c.at ? ` · ${c.at}` : ''} · {c.jobs ? t('incidents.crewJobs', { count: c.jobs }) : t('incidents.crewFree')}
            </Badge>
          ))}
        </Group>
      )}
      {board.error && (
        <Alert color="down" role="alert" mb="md">
          {t('common.error', { message: board.error.message })}
        </Alert>
      )}
      {board.isPending ? (
        <Loader size="sm" />
      ) : (
        board.data && (
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
            {COLUMNS.map((status) => {
              const column = items.filter((i) => i.status === status)
              const shown = status === 'fixed' ? column.slice(0, FIXED_SHOWN) : column
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
                      onChange={(c) => change.mutate({ id: i.id, change: c })} onDispatch={() => send.mutate(i.id)} />
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
