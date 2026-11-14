import { Alert, Badge, Button, Code, Group, Loader, Paper, Stack, Table, Text, TextInput, Textarea, Title } from '@mantine/core'
import { IconTrophy } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { MatchZone, PlanDrawing, QosHints, TournamentData } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { compact } from './tournament/seats'

function HallPlan({ drawing, label }: { drawing: PlanDrawing; label: string }) {
  return (
    <svg viewBox={drawing.box} role="img" aria-label={label} className="fb-match-plan">
      {drawing.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            {b.cells.map((c) => (
              <rect key={c.seat} className={c.on ? 'cell match' : 'cell'} data-seat={c.seat} x={c.x + 1} y={c.y + 1}
                width={drawing.cell - 2} height={drawing.cell - 2} rx={3}><title>{c.seat}</title></rect>
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={b.cy - Math.max(b.w, b.h) / 2 - 18}>{b.name}</text>}
        </g>
      ))}
    </svg>
  )
}

function ZoneForm({ zone, onDone, onCancel }: { zone?: MatchZone; onDone: () => void; onCancel?: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState(zone?.name ?? '')
  const [seats, setSeats] = useState(zone ? [...zone.blocks, ...compact(zone.seats)].join(', ') : '')
  const [note, setNote] = useState(zone?.note ?? '')
  const save = useMutation({
    mutationFn: () => zone
      ? patch<MatchZone>(`/api/tournament/zones/${zone.id}`, { name, seats, note })
      : post<MatchZone>('/api/tournament/zones', { name, seats, note }),
    onSuccess: () => {
      if (!zone) { setName(''); setSeats(''); setNote('') }
      onDone()
    },
  })
  return (
    <Stack gap="xs">
      <Group grow align="flex-start">
        <TextInput label={t('tournament.name')} placeholder={t('tournament.namePlaceholder')} value={name} maxLength={60}
          onChange={(e) => setName(e.currentTarget.value)} required />
        <TextInput label={t('tournament.seats')} description={t('tournament.seatsHelp')} placeholder="B, A-1..A-16" value={seats}
          onChange={(e) => setSeats(e.currentTarget.value)} required />
      </Group>
      <Textarea label={t('tournament.note')} value={note} maxLength={300} autosize minRows={1} onChange={(e) => setNote(e.currentTarget.value)} />
      {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
      <Group justify="flex-end">
        {onCancel && <Button variant="default" onClick={onCancel}>{t('common.cancel')}</Button>}
        <Button loading={save.isPending} disabled={!name.trim() || !seats.trim()} onClick={() => save.mutate()}>
          {zone ? t('tournament.save') : t('tournament.add')}
        </Button>
      </Group>
    </Stack>
  )
}

function Qos() {
  const { t } = useTranslation()
  const [asked, setAsked] = useState(false)
  const hints = useQuery({ queryKey: qk.qos, queryFn: () => get<QosHints>('/api/tournament/qos'), enabled: asked })
  const h = hints.data
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb="xs">
        <Title order={2} size="h4">{t('tournament.qos')}</Title>
        <Button variant="default" size="xs" loading={hints.isFetching} onClick={() => (asked ? void hints.refetch() : setAsked(true))}>
          {t('tournament.qosLookUp')}
        </Button>
      </Group>
      <Text size="sm" c="dimmed" mb="sm">{t('tournament.qosHelp')}</Text>
      {hints.error && <Alert color="down" role="alert">{hints.error.message}</Alert>}
      {h && !h.available && <Text size="sm" c="dimmed">{t('tournament.qosNoMonitoring')}</Text>}
      {h && h.available && h.switches.length === 0 && <Text size="sm" c="dimmed">{t('tournament.qosNone')}</Text>}
      {h && h.switches.length > 0 && (
        <Table.ScrollContainer minWidth={520}>
          <Table striped>
            <Table.Thead><Table.Tr><Table.Th>{t('tournament.switch')}</Table.Th><Table.Th>{t('tournament.ports')}</Table.Th><Table.Th>{t('tournament.uplinks')}</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {h.switches.map((s) => (
                <Table.Tr key={s.switch_id}>
                  <Table.Td fw={600}>{s.switch}</Table.Td>
                  <Table.Td><Code>{s.ports.map((p) => p.port).join(', ')}</Code><Text size="xs" c="dimmed">{s.ports.map((p) => p.seat).join(', ')}</Text></Table.Td>
                  <Table.Td>{s.uplinks.length ? <Code>{s.uplinks.join(', ')}</Code> : '–'}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {h && h.missing.length > 0 && <Text size="xs" c="dimmed" mt="xs">{t('tournament.qosMissing', { seats: h.missing.join(', ') })}</Text>}
    </Paper>
  )
}

/** Tournament awareness: which seats are match seats, and what that changes. */
export default function Tournament() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const [editing, setEditing] = useState<string | null>(null)
  const query = useQuery({ queryKey: qk.tournament, queryFn: () => get<TournamentData>('/api/tournament') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.tournament })
  useLiveEvent('tournament.changed', refresh)
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/tournament/zones/${id}`), onSuccess: refresh })
  const data = query.data
  const count = data ? Object.keys(data.seats).length : 0

  return (
    <Layout title={t('tournament.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('tournament.title')} desc={t('tournament.intro')} />
      <Stack gap="md">
        {(query.error ?? remove.error) && <Alert color="down" role="alert">{t('common.error', { message: (query.error ?? remove.error)!.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : data && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb={4}>{t('tournament.what')}</Title>
              <Stack gap={2}>
                <Text size="sm">• {t('tournament.what1')}</Text>
                <Text size="sm">• {t('tournament.what2')}</Text>
                <Text size="sm">• {t('tournament.what3')}</Text>
              </Stack>
            </Paper>
            <Paper withBorder radius="lg" p="md">
              <Group justify="space-between" mb="xs">
                <Title order={2} size="h4">{t('tournament.zones')}</Title>
                <Badge variant="light" color="warn" tt="none">{t('tournament.count', { count })}</Badge>
              </Group>
              {data.zones.length === 0 && <Text size="sm" c="dimmed" mb="sm">{t('tournament.empty')}</Text>}
              <Stack gap="sm">
                {data.zones.map((z) => editing === z.id ? (
                  <ZoneForm key={z.id} zone={z} onDone={() => { setEditing(null); refresh() }} onCancel={() => setEditing(null)} />
                ) : (
                  <Group key={z.id} justify="space-between" align="flex-start" wrap="nowrap">
                    <Stack gap={2} style={{ minWidth: 0 }}>
                      <Text fw={600}><IconTrophy size={16} style={{ verticalAlign: '-2px' }} aria-hidden="true" /> {z.name}</Text>
                      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
                        {[...z.blocks.map((b) => t('tournament.block', { name: b })), ...compact(z.seats)].join(', ')}
                      </Text>
                      {z.note && <Text size="xs" c="dimmed">{z.note}</Text>}
                    </Stack>
                    {canEdit && (
                      <Group gap="xs" wrap="nowrap">
                        <Button size="xs" variant="default" onClick={() => setEditing(z.id)}>{t('tournament.edit')}</Button>
                        <ConfirmButton size="xs" variant="subtle" danger label={t('tournament.remove')}
                          question={t('tournament.removeQuestion', { name: z.name })} onConfirm={() => remove.mutate(z.id)} />
                      </Group>
                    )}
                  </Group>
                ))}
              </Stack>
              {canEdit && editing === null && (
                <Paper withBorder radius="md" p="sm" mt="md" bg="var(--color-raised)">
                  <Text size="sm" fw={600} mb={4}>{t('tournament.newZone')}</Text>
                  <ZoneForm onDone={refresh} />
                </Paper>
              )}
            </Paper>
            {data.plans.map((p) => (
              <Paper key={p.hall} withBorder radius="lg" p="md">
                <Group justify="space-between" mb="xs">
                  <Text size="sm" fw={600}>{p.name}</Text>
                  <Text size="xs" c="dimmed"><span className="fb-match-key" /> {t('tournament.count', { count: p.match })}</Text>
                </Group>
                <HallPlan drawing={p.drawing} label={t('tournament.planLabel', { hall: p.name })} />
              </Paper>
            ))}
            {count > 0 && <Qos />}
          </>
        )}
      </Stack>
    </Layout>
  )
}
