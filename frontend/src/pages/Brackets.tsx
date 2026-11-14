import {
  Alert, Anchor, Badge, Button, Group, Loader, Modal, NumberInput, Paper, SegmentedControl, Select, Stack, Text, TextInput,
  Textarea, Title,
} from '@mantine/core'
import { IconDownload, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { Bracket, BracketMatch, BracketsData } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { roundName } from './tournament/brackets'

function NewBracket({ zones, onDone }: { zones: BracketsData['zones']; onDone: (id?: string) => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [teams, setTeams] = useState('')
  const [zone, setZone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => post<Bracket>('/api/tournament/brackets', { name, teams, zone_id: zone }),
    onSuccess: (b) => onDone(b.id),
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="sm">
        <Title order={2} size="h4">{t('brackets.new')}</Title>
        <Group grow align="flex-start">
          <TextInput label={t('brackets.name')} required maxLength={60} value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Select label={t('brackets.zone')} clearable placeholder={t('brackets.noZone')} value={zone} onChange={setZone}
            data={zones.map((z) => ({ value: z.id, label: z.name }))} />
        </Group>
        <Textarea label={t('brackets.teams')} description={t('brackets.teamsHelp')} autosize minRows={4} value={teams}
          onChange={(e) => setTeams(e.currentTarget.value)} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group gap="xs">
          <Button loading={save.isPending} disabled={!name.trim() || !teams.trim()} onClick={() => save.mutate()}>{t('brackets.create')}</Button>
          <Button variant="default" onClick={() => onDone()}>{t('brackets.cancel')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

function MatchEditor({ bracket, match, onClose }: { bracket: Bracket; match: BracketMatch; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [a, setA] = useState<number | string>(match.a.score ?? '')
  const [b, setB] = useState<number | string>(match.b.score ?? '')
  const [winner, setWinner] = useState<string>(match.winner ?? '')
  const [status, setStatus] = useState<string>(match.status)
  const [seats, setSeats] = useState(match.seats.join(', '))
  const [station, setStation] = useState(match.station)
  const save = useMutation({
    mutationFn: () => patch(`/api/tournament/brackets/${bracket.id}/matches/${match.id}`, {
      a_score: a === '' ? null : a, b_score: b === '' ? null : b, winner: winner || null, status, seats, station,
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.brackets }); onClose() },
  })
  const side = (s: 'a' | 'b') => match[s].name ?? t('brackets.tbd')
  return (
    <Stack gap="sm">
      <Group grow>
        <NumberInput label={side('a')} min={0} max={9999} value={a} onChange={setA} />
        <NumberInput label={side('b')} min={0} max={9999} value={b} onChange={setB} />
      </Group>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('brackets.winner')}</Text>
        <SegmentedControl fullWidth value={winner} onChange={setWinner} aria-label={t('brackets.winner')}
          data={[{ value: '', label: t('brackets.open') },
            { value: 'a', label: side('a'), disabled: !match.a.name }, { value: 'b', label: side('b'), disabled: !match.b.name }]} />
      </div>
      {!winner && (
        <Select label={t('brackets.status')} value={status} allowDeselect={false} onChange={(v) => setStatus(v ?? 'waiting')}
          data={[{ value: 'waiting', label: t('brackets.waiting') }, { value: 'live', label: t('brackets.live') }]} />
      )}
      <TextInput label={t('brackets.seats')} description={t('brackets.seatsHelp')} value={seats} onChange={(e) => setSeats(e.currentTarget.value)} />
      <TextInput label={t('brackets.station')} maxLength={60} value={station} onChange={(e) => setStation(e.currentTarget.value)} />
      {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
      <Group gap="xs">
        <Button loading={save.isPending} onClick={() => save.mutate()}>{t('brackets.save')}</Button>
        <Button variant="default" onClick={onClose}>{t('brackets.cancel')}</Button>
      </Group>
    </Stack>
  )
}

function MatchCard({ match, onOpen, roundOne }: { match: BracketMatch; onOpen?: () => void; roundOne: boolean }) {
  const { t } = useTranslation()
  const row = (s: 'a' | 'b') => {
    const team = match[s]
    const cls = match.winner === s ? 'won' : match.winner ? 'lost' : ''
    return (
      <div className={`fb-bracket-team ${cls} ${team.name ? '' : 'tbd'}`}>
        <span>{team.name ?? (roundOne && match.winner ? t('brackets.bye') : t('brackets.tbd'))}</span>
        <b>{team.score ?? ''}</b>
      </div>
    )
  }
  const body = (
    <>
      {match.status === 'live' && <span className="fb-bracket-live">{t('brackets.live')}</span>}
      {row('a')}
      {row('b')}
    </>
  )
  return (
    <div className={`fb-bracket-match ${match.status}`} data-match={match.id}>
      {onOpen ? (
        <button type="button" className="fb-bracket-open" onClick={onOpen}
          aria-label={t('brackets.edit', { a: match.a.name ?? t('brackets.tbd'), b: match.b.name ?? t('brackets.tbd') })}>{body}</button>
      ) : body}
      {(match.station || match.seats.length > 0) && (
        <div className="fb-bracket-meta">
          {match.station && <span>{match.station}</span>}
          {match.seats.slice(0, 3).map((s) => <Anchor key={s} href={`/?seat=${encodeURIComponent(s)}`} size="xs">{s}</Anchor>)}
          {match.seats.length > 3 && <span>+{match.seats.length - 3}</span>}
          {match.zones.map((z) => <Anchor key={z} href="/tournament" size="xs">{z}</Anchor>)}
        </div>
      )}
    </div>
  )
}

function BracketView({ bracket, data, canEdit, onRemoved }: { bracket: Bracket; data: BracketsData; canEdit: boolean; onRemoved: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [open, setOpen] = useState<BracketMatch | null>(null)
  const imported = bracket.source === 'import'
  const editable = canEdit && !imported
  const move = useMutation({
    mutationFn: (zone: string | null) => patch(`/api/tournament/brackets/${bracket.id}`, { zone_id: zone }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.brackets }),
  })
  const remove = useMutation({ mutationFn: () => del(`/api/tournament/brackets/${bracket.id}`), onSuccess: onRemoved })
  const final = bracket.rounds[bracket.rounds.length - 1][0]
  const champion = final.winner ? final[final.winner].name : null
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Title order={2} size="h3">{bracket.name}</Title>
          {imported && <Badge mt={4} variant="outline" color="gray" tt="none">{t('brackets.fromPlugin', { plugin: bracket.plugin })}</Badge>}
        </div>
        <Group gap="xs" align="flex-end">
          <Select size="xs" label={t('brackets.zone')} clearable placeholder={t('brackets.noZone')} value={bracket.zone_id} disabled={!canEdit}
            data={data.zones.map((z) => ({ value: z.id, label: z.name }))} onChange={(v) => move.mutate(v)} />
          {canEdit && <ConfirmButton size="xs" variant="subtle" danger label={t('brackets.remove')}
            question={t('brackets.removeQuestion', { name: bracket.name })} onConfirm={() => remove.mutate()} />}
        </Group>
      </Group>
      {(move.error || remove.error) && <Alert color="down" role="alert" mb="sm">{(move.error || remove.error)!.message}</Alert>}
      <div className="fb-bracket-scroll">
        <div className="fb-bracket" style={{ gridTemplateColumns: `repeat(${bracket.rounds.length + (champion ? 1 : 0)}, minmax(190px, 1fr))` }}>
          {bracket.rounds.map((rnd, r) => (
            <div key={r} className="fb-bracket-round">
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={6}>{t(roundName(r, bracket.rounds.length), { n: r + 1 })}</Text>
              <div className="fb-bracket-matches">
                {rnd.map((m) => <MatchCard key={m.id} match={m} roundOne={r === 0} onOpen={editable ? () => setOpen(m) : undefined} />)}
              </div>
            </div>
          ))}
          {champion && (
            <div className="fb-bracket-round">
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={6}>{t('brackets.champion')}</Text>
              <div className="fb-bracket-matches"><div className="fb-bracket-champion">{champion}</div></div>
            </div>
          )}
        </div>
      </div>
      {editable && <Text size="xs" c="dimmed" mt="xs">{t('brackets.clickHint')}</Text>}
      <Modal opened={!!open} onClose={() => setOpen(null)} title={open ? `${open.a.name ?? t('brackets.tbd')} – ${open.b.name ?? t('brackets.tbd')}` : ''}>
        {open && <MatchEditor key={open.id} bracket={bracket} match={open} onClose={() => setOpen(null)} />}
      </Modal>
    </Paper>
  )
}

/** Tournament brackets (issue #107): entered here or imported from a tournament tool's plugin. */
export default function Brackets() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const [params, setParams] = useSearchParams()
  const [adding, setAdding] = useState(false)
  const query = useQuery({ queryKey: qk.brackets, queryFn: () => get<BracketsData>('/api/tournament/brackets') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.brackets })
  useLiveEvent('brackets.changed', refresh)
  const sync = useMutation({ mutationFn: () => post<{ count: number; errors: string[] }>('/api/tournament/brackets/import'), onSuccess: refresh })
  const d = query.data
  const current = d?.brackets.find((b) => b.id === params.get('id')) ?? d?.brackets[0]
  const pick = (id: string) => setParams({ id }, { replace: true })

  return (
    <Layout title={t('brackets.title')} back={{ href: '/tournament', label: t('tournament.title') }}>
      <PageHead title={t('brackets.title')} desc={t('brackets.intro')}
        actions={canEdit ? (
          <Group gap="xs">
            {d && d.sources.length > 0 && (
              <Button variant="default" leftSection={<IconDownload size={16} />} loading={sync.isPending} onClick={() => sync.mutate()}>
                {t('brackets.import', { plugins: d.sources.join(', ') })}
              </Button>
            )}
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>{t('brackets.new')}</Button>
          </Group>
        ) : undefined} />
      {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
      {sync.error && <Alert color="down" role="alert" mb="sm">{sync.error.message}</Alert>}
      {sync.data && (
        <Alert color={sync.data.errors.length ? 'warn' : 'up'} role="status" mb="sm" withCloseButton onClose={() => sync.reset()}>
          {t('brackets.imported', { count: sync.data.count })} {sync.data.errors.join(' ')}
        </Alert>
      )}
      {query.isPending || !d ? <Loader aria-label={t('common.loading')} /> : (
        <Stack gap="md">
          <Text size="sm">
            {d.public
              ? <>{t('brackets.publicOn')} <Anchor href="/bracket" target="_blank">/bracket</Anchor> · <Anchor href="/bracket?screen=1" target="_blank">{t('brackets.bigScreen')}</Anchor></>
              : t('brackets.publicOff')}
          </Text>
          {adding && <NewBracket zones={d.zones} onDone={(id) => { setAdding(false); refresh(); if (id) pick(id) }} />}
          {d.brackets.length > 1 && (
            <SegmentedControl value={current?.id} onChange={pick} aria-label={t('brackets.title')}
              data={d.brackets.map((b) => ({ value: b.id, label: b.name }))} />
          )}
          {current ? <BracketView key={current.id} bracket={current} data={d} canEdit={canEdit} onRemoved={() => { setParams({}); refresh() }} />
            : !adding && <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('brackets.empty')}</Text></Paper>}
        </Stack>
      )}
    </Layout>
  )
}
