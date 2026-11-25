import { Anchor, Badge, Group, Text } from '@mantine/core'
import { IconNote } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { Incident, IncidentBoard } from '@/api/types'
import { ago, clock } from '@/lib/time'
import { fixedAfter, isSnoozed, isWaiting, unseenFor, waitedFor } from './waiting'
import { mbit, notSeenFor, planLinkOf, whereOf } from './where'

/** What an incident's badges say. ``full`` adds the team, where it came from and how often the
 *  seat came back; the board's cards keep to where it is and what needs a look (issue #887). */
export function IncidentBadges({ i, board, now, full = false }: { i: Incident; board: IncidentBoard; now: number; full?: boolean }) {
  const { t } = useTranslation()
  const teamName = board.teams.find((x) => x.id === i.team)?.name
  // The how-many-th incident at this seat (issue #314): a seat that keeps coming back has a cable or port to check.
  const atSeat = i.seat ? board.incidents.filter((x) => x.seat === i.seat && x.created_at <= i.created_at).length : 0
  const where = whereOf(i, t)
  const planLink = planLinkOf(i)
  return (
    <Group gap={6}>
      {/* Seats and switches open on the floor plan, in their own hall (issue #206). */}
      {planLink
        ? <Badge component="a" href={planLink}
            variant="light" color="trace" tt="none" style={{ cursor: 'pointer' }} title={t('incidents.openOnPlan')}>{where}</Badge>
        : <Badge variant="light" color="trace" tt="none">{where}</Badge>}
      {full && (teamName ? <Badge variant="outline" tt="none">{teamName}</Badge>
        : <Badge variant="outline" color="warn" tt="none">{t('incidents.noTeam')}</Badge>)}
      {full && i.source === 'helpdesk' && <Badge variant="light" color="bit" tt="none">{t('incidents.fromSeat')}</Badge>}
      {full && i.source === 'power' && <Badge variant="light" color="warn" tt="none">{t('incidents.fromPower')}</Badge>}
      {full && i.source === 'discord' && <Badge variant="light" color="gray" tt="none">{t('incidents.fromDiscord')}</Badge>}
      {i.reports > 1 && <Badge variant="light" color="warn" tt="none">{t('incidents.reports', { count: i.reports })}</Badge>}
      {/* Opens every incident at this seat (issue #338), fixed ones too, to see what was tried. */}
      {full && atSeat > 1 && (
        <Badge component="a" href={`/incidents?q=${encodeURIComponent(`seat:${i.seat}`)}`} variant="outline" color="warn" tt="none"
          title={t('incidents.againHint')} style={{ cursor: 'pointer' }}>{t('incidents.again', { n: atSeat })}</Badge>
      )}
      {isSnoozed(i, now) && (
        <Badge variant="light" color="gray" tt="none">{t('incident.snoozedUntil', { time: clock(i.snoozed_until!) })}</Badge>
      )}
      {i.dismissed && <Badge variant="light" color="gray" tt="none">{t('incident.notAProblem')}</Badge>}
      {isWaiting(i, now) && <Badge variant="filled" color="warn" tt="none">{waitedFor(now - i.created_at, t)}</Badge>}
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
      {/* The problem it was made from ended by itself (issue #882): it may work again already. */}
      {i.problem_over_at && i.status !== 'fixed' && (
        <Badge variant="light" color="up" tt="none" title={t('incidentProblem.overHint')}>{t('incidentProblem.over', { ago: ago(i.problem_over_at) })}</Badge>
      )}
      {/* Saves a walk: the attendee says it fixed itself. Only the crew marks it fixed (issue #372). */}
      {i.seat_ok_at && i.status !== 'fixed' && (
        <Badge variant="light" color="up" tt="none" title={t('incidents.seatOkHint')}>{t('incidents.seatOk', { ago: ago(i.seat_ok_at) })}</Badge>
      )}
    </Group>
  )
}

/** Who has it and how far they are: "Assigned to ben · on the way", "Fixed after 12 min". */
export function OwnerLine({ i, now }: { i: Incident; now: number }) {
  const { t } = useTranslation()
  const unseen = unseenFor(i, now)
  return (
    <Text size="sm" c="dimmed">
      {i.assignee ? t('incidents.assignedTo', { name: i.assignee })
        : i.status === 'fixed' && i.fixed_at ? fixedAfter(i.fixed_at - i.created_at, t, true) : t('incidents.unassigned')}
      {i.assignee && i.dispatched_at && i.status !== 'fixed' && unseen == null && ` · ${i.taken_at ? t('incidents.onTheWay') : t('incidents.notSeenYet')}`}
      {unseen != null && <> · <Text span size="sm" c="warn" fw={600}>{notSeenFor(unseen, t)}</Text></>}
      {i.status === 'fixed' && i.fixed_at && i.assignee && ` · ${fixedAfter(i.fixed_at - i.created_at, t)}`}
    </Text>
  )
}

/** What Floorbit knew when it was filed: the seat's port, the speed test, the seat's note, the problem. */
export function IncidentDetails({ i }: { i: Incident }) {
  const { t } = useTranslation()
  const snap = i.snapshot
  return (
    <>
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
      {i.from_problem && (
        <Anchor size="sm" href={`/problems/${encodeURIComponent(i.from_problem)}`}>{t('incidents.fromProblem')}</Anchor>
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
    </>
  )
}
