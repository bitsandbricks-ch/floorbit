import { Anchor, Badge, Button, Group, Paper, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconBook, IconNote } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Incident, IncidentBoard, IncidentPeople } from '@/api/types'
import { useNowSeconds } from '@/components/useNowSeconds'
import { fixedAfter, isWaiting, unseenFor, waitedFor } from './waiting'
import { ago } from '@/lib/time'
import { incidentTitle } from '@/lib/incidentTitle'

export type IncidentChange = Partial<{ status: string; assignee: string | null; team: string | null; note: string }>


/** Open this long with nobody on it, an incident says so (issue #296). */

/** "not seen for 7 min", or with hours. */
function notSeenFor(seconds: number, t: (k: string, o?: Record<string, unknown>) => string) {
  const mins = Math.floor(seconds / 60)
  return mins < 60 ? t('incidents.notSeenFor', { count: mins }) : t('incidents.notSeenForLong', { h: Math.floor(mins / 60), m: mins % 60 })
}

/** Whole Mbit/s from 100 on: "912", not "912.4". */
function mbit(n: number | null) {
  return n == null ? '?' : n >= 100 ? String(Math.round(n)) : String(n)
}

/** One incident on the board, with the actions this account may take on it. */
export function IncidentCard({
  incident: i,
  board,
  people,
  me,
  busy,
  onChange,
  onDispatch,
}: {
  incident: Incident
  board: IncidentBoard
  people: IncidentPeople | undefined
  me: string | undefined
  busy: boolean
  onChange: (change: IncidentChange) => void
  onDispatch?: () => void
}) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')
  const teamName = board.teams.find((x) => x.id === i.team)?.name
  // The how-many-th incident at this seat (issue #314): a seat that keeps coming back has a cable or port to check.
  const atSeat = i.seat ? board.incidents.filter((x) => x.seat === i.seat && x.created_at <= i.created_at).length : 0
  const where = i.seat ? t('incidents.seat', { seat: i.seat })
    : i.circuit_id ? t('incidents.circuit', { name: i.circuit_name ?? i.circuit_id })
    : t('incidents.switch', { name: i.switch_name ?? i.switch_id })
  const planLink = i.seat ? `/plan?seat=${encodeURIComponent(i.seat)}`
    : !i.circuit_id && i.switch_name ? `/plan?switch=${encodeURIComponent(i.switch_name)}` : null
  const snap = i.snapshot
  const assignable = (people?.[i.team ?? ''] ?? []).map((p) => ({ value: p.username, label: p.display_name }))
  const lastNote = i.notes[i.notes.length - 1]
  const now = useNowSeconds()
  const unseen = unseenFor(i, now)
  const waiting = isWaiting(i, now)

  return (
    <Paper withBorder radius="lg" p="sm" data-incident={i.id}>
      <Stack gap={6}>
        <Group justify="space-between" gap="xs" wrap="nowrap" align="flex-start">
          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{incidentTitle(i.title, t)}</Text>
          <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{ago(i.created_at)}</Text>
        </Group>
        <Group gap={6}>
          {/* Seats and switches open on the Seats page, in their own hall (issue #206). */}
          {planLink
            ? <Badge component="a" href={planLink}
                variant="light" color="trace" tt="none" style={{ cursor: 'pointer' }} title={t('incidents.openOnPlan')}>{where}</Badge>
            : <Badge variant="light" color="trace" tt="none">{where}</Badge>}
          {i.match && <Badge color="warn" variant="filled" tt="none">{t('incidents.match', { zone: i.match })}</Badge>}
          {teamName ? <Badge variant="outline" tt="none">{teamName}</Badge> : <Badge variant="outline" color="warn" tt="none">{t('incidents.noTeam')}</Badge>}
          {i.source === 'helpdesk' && <Badge variant="light" color="bit" tt="none">{t('incidents.fromSeat')}</Badge>}
          {i.source === 'power' && <Badge variant="light" color="warn" tt="none">{t('incidents.fromPower')}</Badge>}
          {i.source === 'discord' && <Badge variant="light" color="gray" tt="none">{t('incidents.fromDiscord')}</Badge>}
          {i.reports > 1 && <Badge variant="light" color="warn" tt="none">{t('incidents.reports', { count: i.reports })}</Badge>}
          {/* Opens every incident at this seat (issue #338), fixed ones too, to see what was tried. */}
          {atSeat > 1 && (
            <Badge component="a" href={`/incidents?q=${encodeURIComponent(`seat:${i.seat}`)}`} variant="outline" color="warn" tt="none"
              title={t('incidents.againHint')} style={{ cursor: 'pointer' }}>{t('incidents.again', { n: atSeat })}</Badge>
          )}
          {waiting && <Badge variant="filled" color="warn" tt="none">{waitedFor(now - i.created_at, t)}</Badge>}
          {/* Part of an outage, not a cable: look at the switch first (issue #386). */}
          {i.outage && (
            <Badge variant="filled" color="down" tt="none" title={t('incidents.outageHint')}>
              {t('incidents.outage', { switch: i.outage.switch, ago: ago(i.outage.since) })}
            </Badge>
          )}
          {/* Filed during an outage that is over: it may work again already (issue #390). */}
          {i.back_up && (
            <Badge variant="light" color="up" tt="none" title={t('incidents.backUpHint')}>
              {t('incidents.backUp', { switch: i.back_up.switch, ago: ago(i.back_up.since) })}
            </Badge>
          )}
          {/* Saves a walk: the attendee says it fixed itself. Only the crew marks it fixed (issue #372). */}
          {i.seat_ok_at && i.status !== 'fixed' && (
            <Badge variant="light" color="up" tt="none" title={t('incidents.seatOkHint')}>{t('incidents.seatOk', { ago: ago(i.seat_ok_at) })}</Badge>
          )}
        </Group>
        {snap && (
          <Text size="sm" c={snap.known && snap.link && snap.link !== 'up' ? 'var(--color-down)' : 'dimmed'}>
            {snap.known
              ? t('incidents.snapshot', {
                  switch: snap.switch, port: snap.port, link: t(`incidents.link.${snap.link ?? 'unknown'}`, { defaultValue: snap.link ?? '' }),
                  mac: snap.mac_seen ? t('incidents.macSeen') : t('incidents.macMissing'),
                })
              : t('incidents.snapshotUnknown', { reason: snap.reason })}
          </Text>
        )}
        {i.speedtest && (
          <Text size="sm" c="dimmed" data-speedtest>
            {t('incidents.speedtest', {
              down: mbit(i.speedtest.down_mbps), up: mbit(i.speedtest.up_mbps), ping: i.speedtest.ping_ms ?? '?', ago: ago(i.speedtest.at),
            })}
          </Text>
        )}
        {i.seat_note && (
          <Text size="sm" data-seat-note style={{ overflowWrap: 'anywhere' }}>
            <IconNote size={14} color="var(--color-warn)" style={{ verticalAlign: -2, marginRight: 4 }} aria-hidden />
            <Text span fw={600}>{t('incidents.seatNote')}</Text> {i.seat_note.text}{' '}
            <Text span size="xs" c="dimmed">{[i.seat_note.by, ago(i.seat_note.at)].filter(Boolean).join(' · ')}</Text>
          </Text>
        )}
        {i.runbook && (
          <Anchor size="sm" href={`/runbooks?open=${encodeURIComponent(i.runbook.id)}`} data-runbook>
            <IconBook size={14} style={{ verticalAlign: -2, marginRight: 4 }} />{t('incidents.runbook', { title: i.runbook.title })}
          </Anchor>
        )}
        {lastNote && <Text size="sm">“{lastNote.text}” <Text span size="xs" c="dimmed">{lastNote.by ?? (i.source === 'power' ? 'Floorbit' : t('incidents.attendee'))}</Text></Text>}
        <Text size="sm" c="dimmed">
          {i.assignee ? t('incidents.assignedTo', { name: i.assignee })
            : i.status === 'fixed' && i.fixed_at ? fixedAfter(i.fixed_at - i.created_at, t, true) : t('incidents.unassigned')}
          {i.assignee && i.dispatched_at && i.status !== 'fixed' && unseen == null && ` · ${i.taken_at ? t('incidents.onTheWay') : t('incidents.notSeenYet')}`}
          {unseen != null && <> · <Text span size="sm" c="warn" fw={600}>{notSeenFor(unseen, t)}</Text></>}
          {i.status === 'fixed' && i.fixed_at && i.assignee && ` · ${fixedAfter(i.fixed_at - i.created_at, t)}`}
        </Text>
        {i.can_work && (
          <>
            <Group gap="xs">
              {i.status === 'open' && (
                <Button size="xs" loading={busy} onClick={() => onChange({ status: 'assigned', assignee: me ?? null })}>
                  {t('incidents.take')}
                </Button>
              )}
              {i.status !== 'fixed' && (
                <Button size="xs" variant="default" loading={busy} onClick={() => onChange({ status: 'fixed' })}>
                  {t('incidents.fixed')}
                </Button>
              )}
              {i.status === 'fixed' && (
                <Button size="xs" variant="default" loading={busy} onClick={() => onChange({ status: 'open' })}>
                  {t('incidents.reopen')}
                </Button>
              )}
            </Group>
            {i.can_assign && i.status === 'open' && !i.assignee && onDispatch && (
              <Button size="xs" variant="light" loading={busy} onClick={onDispatch}>{t('incidents.sendNearest')}</Button>
            )}
            {i.can_assign && i.status !== 'fixed' && (
              <Group gap="xs" grow>
                <Select size="xs" aria-label={t('incidents.assignee')} placeholder={t('incidents.assignee')} data={assignable}
                  value={i.assignee} clearable onChange={(v) => onChange({ assignee: v })} />
                <Select size="xs" aria-label={t('incidents.team')} placeholder={t('incidents.team')}
                  data={board.teams.filter((x) => board.assign_teams.includes(x.id)).map((x) => ({ value: x.id, label: x.name }))}
                  value={i.team} onChange={(v) => v && onChange({ team: v })} />
              </Group>
            )}
            <TextInput size="xs" aria-label={t('incidents.addNote')} placeholder={t('incidents.addNote')} value={note} maxLength={2000}
              onChange={(e) => setNote(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && note.trim()) {
                  onChange({ note: note.trim() })
                  setNote('')
                }
              }} />
          </>
        )}
      </Stack>
    </Paper>
  )
}
