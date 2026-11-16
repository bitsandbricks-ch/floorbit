import { Alert, Anchor, Badge, Button, CopyButton, Group, Loader, Modal, Paper, SegmentedControl, Select, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconBellOff, IconCheck, IconCopy } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useProblems } from '@/api/queries'
import type { Problem } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { StatCard } from '@/components/StatCard'
import { useNowSeconds } from '@/components/useNowSeconds'
import { problemsText } from './problems/format'

const MINUTES = ['30', '60', '240', '720', '1440']
type T = (k: string, o?: Record<string, unknown>) => string

function ago(ts: number, t: T) {
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60))
  if (mins < 1) return t('problems.justNow')
  if (mins < 60) return t('problems.minutesAgo', { count: mins })
  return t('problems.hoursAgo', { count: Math.round(mins / 60) })
}

/** A mute this close to its end gets a badge, so +30 min is pressed before the alerts come back (issue #266). */
const ENDING_SOON = 10 * 60


const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

function Row({ p, canMute, busy, onMute, onReport }: {
  p: Problem; canMute: boolean; busy: boolean; onMute: () => void; onReport?: () => void
}) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="md" p="sm" component="article" aria-label={p.title}
      className={`fb-problem ${p.muted ? 'muted' : p.level}`}>
      {/* Wraps on a phone: a switch problem has up to four actions, wider than the screen. */}
      <Group justify="space-between" align="flex-start" gap="xs">
        <Stack gap={2} style={{ minWidth: 0, flex: '1 1 240px' }}>
          <Group gap="xs">
            <Badge variant="light" color={p.level === 'down' ? 'down' : 'warn'} tt="none">{t(`problems.kind.${p.kind}`)}</Badge>
            <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{p.title}</Text>
            {p.match && <Badge color="warn" variant="filled" tt="none">{t('problems.match', { zone: p.match })}</Badge>}
          </Group>
          {p.where && <Text size="sm" c="dimmed">{p.where}</Text>}
          {p.muted && (
            <Text size="xs" c="dimmed">
              <IconBellOff size={12} style={{ verticalAlign: '-1px' }} aria-hidden="true" />{' '}
              {t('problems.mutedUntil', { time: clock(p.muted.until), who: p.muted.by ?? '?' })}
              {p.muted.reason ? ` · ${p.muted.reason}` : ''}
            </Text>
          )}
        </Stack>
        <Group gap="xs">
          {p.since && <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('problems.since', { ago: ago(p.since, t) })}</Text>}
          {p.link && <Button size="xs" variant="default" component="a" href={p.link}>{t('problems.open')}</Button>}
          {/* An offline switch becomes an incident in one click, or links the open one (issue #278). */}
          {p.incident && (
            <Button size="xs" variant="subtle" component="a" href={`/incidents?q=${encodeURIComponent(p.kind === 'switch' && p.name ? `switch:${p.name}` : p.name ?? p.where)}`}>
              {t('problems.incidentOpen')}
            </Button>
          )}
          {onReport && p.kind === 'switch' && p.incident === null && (
            <Button size="xs" variant="subtle" onClick={onReport} disabled={busy}>{t('problems.report')}</Button>
          )}
          {canMute && (!!p.mute_id || p.kind === 'switch') && !p.muted && (
            <Button size="xs" variant="subtle" leftSection={<IconBellOff size={14} />} onClick={onMute} disabled={busy}>{t('problems.mute')}</Button>
          )}
        </Group>
      </Group>
    </Paper>
  )
}

type MuteTarget = { id: string; name: string; kind: 'switch' | 'health' }

function MuteDialog({ target, busy, error, onClose, onSave }: {
  target: MuteTarget | null
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (minutes: number, reason: string) => void
}) {
  const { t } = useTranslation()
  return (
    <Modal opened={!!target} onClose={onClose} title={t('problems.muteTitle', { name: target?.name })} closeButtonProps={{ 'aria-label': t('problems.cancel') }}>
      <MuteForm text={t(target?.kind === 'health' ? 'problems.muteTextService' : 'problems.muteText')}
        busy={busy} error={error} onClose={onClose} onSave={onSave} />
    </Modal>
  )
}

function MuteForm({ text, busy, error, onClose, onSave }: {
  text: string
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (minutes: number, reason: string) => void
}) {
  const { t } = useTranslation()
  const [minutes, setMinutes] = useState<string | null>('60')
  const [reason, setReason] = useState('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(Number(minutes), reason.trim()) }}>
      <Stack gap="sm">
        <Text size="sm">{text}</Text>
        <Select label={t('problems.for')} data={MINUTES.map((m) => ({ value: m, label: t(`problems.minutes.${m}`) }))}
          value={minutes} onChange={setMinutes} allowDeselect={false} />
        <TextInput label={t('problems.reason')} value={reason} maxLength={200} onChange={(e) => setReason(e.currentTarget.value)} />
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('problems.cancel')}</Button>
          <Button type="submit" loading={busy} leftSection={<IconBellOff size={16} />}>{t('problems.mute')}</Button>
        </Group>
      </Stack>
    </form>
  )
}

/** Everything wrong right now, in one list, with mutes for switches and services someone is working on (issues #10, #256). */
export default function Problems() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useProblems()
  const [target, setTarget] = useState<MuteTarget | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const now = useNowSeconds()
  // One kind at a time, kept in the address so a reload or a shared link keeps it (issue #276).
  const [params, setParams] = useSearchParams()
  const shown = params.get('kind') ?? 'all'
  const showKind = (v: string) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    if (v === 'all') next.delete('kind'); else next.set('kind', v)
    return next
  }, { replace: true })
  const refresh = () => void client.invalidateQueries({ queryKey: qk.problems })
  useLiveEvent('monitor.poll', refresh)
  useLiveEvent('alerts.changed', refresh)
  useLiveEvent('power.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('incident.changed', refresh)

  const mute = useMutation({
    // A service on the health wall is muted by its own id (issue #256), a switch by its id.
    mutationFn: (v: MuteTarget & { minutes: number; reason: string }) =>
      post('/api/alerts/mutes', { [v.kind === 'health' ? 'service_id' : 'switch_id']: v.kind === 'health' ? v.id.replace(/^health:/, '') : v.id, minutes: v.minutes, reason: v.reason }),
    onSuccess: () => { setTarget(null); refresh() },
    onError: (e) => setDialogError(e.message),
  })
  const report = useMutation({
    mutationFn: (p: Problem) => post('/api/incidents', { switch_id: p.switch_id, title: p.title }),
    onSuccess: refresh,
  })
  const unmute = useMutation({
    mutationFn: (id: string) => del(`/api/alerts/mutes/${encodeURIComponent(id)}`),
    onSuccess: refresh,
  })
  // Still at it when the mute nears its end: half an hour more, same reason (issue #264).
  const extend = useMutation({
    mutationFn: (id: string) => patch(`/api/alerts/mutes/${encodeURIComponent(id)}`, { minutes: 30 }),
    onSuccess: refresh,
  })
  const data = list.data
  // In the order they first appear, which is worst first.
  const kinds: string[] = data ? [...new Set(data.problems.map((p) => p.kind))] : []
  const visible = data ? data.problems.filter((p) => !kinds.includes(shown) || p.kind === shown) : []
  const error = list.error ?? unmute.error ?? extend.error ?? report.error

  return (
    // Muted problems stay out of the tab count: someone is already on them (issue #214).
    <Layout title={t('problems.title')} back={{ href: '/', label: t('common.floorPlan') }}
      count={data ? (data.counts.down ?? 0) + (data.counts.warn ?? 0) : undefined}>
      <PageHead title={t('problems.title')} desc={t('problems.intro')} actions={data && (
        // For pasting into the crew chat instead of a screenshot (issue #280).
        <CopyButton value={problemsText(visible, data.mutes, t, (ts) => ago(ts, t))} timeout={2000}>
          {({ copied, copy }) => (
            <Button variant="default" size="xs" leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              color={copied ? 'up' : undefined} onClick={copy}>
              {copied ? t('problems.copied') : t('problems.copy')}
            </Button>
          )}
        </CopyButton>
      )} />
      {error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: error.message })}</Alert>}
      {list.isPending || !data ? (
        <Loader size="sm" />
      ) : (
        <Stack gap="md">
          {data.quiet_hours && <Alert color="gray" variant="light">{t('problems.quiet')}</Alert>}
          <div className="fb-stat-row" aria-live="polite">
            {(['down', 'warn', 'muted'] as const).map((k) => (
              <StatCard key={k} label={t(`problems.card.${k}`)} value={String(data.counts[k] ?? 0)}
                tone={data.counts[k] && k !== 'muted' ? k : undefined} />
            ))}
          </div>
          {kinds.length > 1 && (
            <SegmentedControl size="xs" value={kinds.includes(shown) ? shown : 'all'} onChange={showKind} aria-label={t('problems.show')}
              style={{ alignSelf: 'flex-start' }}
              data={['all', ...kinds].map((k) => ({
                value: k,
                label: <span><span>{k === 'all' ? t('problems.all') : t(`problems.kind.${k}`)}</span>{' '}
                  <span className="fb-filter-count">{k === 'all' ? data.problems.length : data.problems.filter((p) => p.kind === k).length}</span></span>,
              }))} />
          )}
          {!data.problems.length ? (
            <Text c="dimmed">{t('problems.none')}</Text>
          ) : (
            <Stack gap="xs">
              {visible.map((p) => (
                <Row key={p.id} p={p} canMute={data.can_mute} busy={mute.isPending || report.isPending}
                  onReport={data.can_report ? () => report.mutate(p) : undefined}
                  onMute={() => { setDialogError(null); setTarget({ id: p.mute_id ?? p.switch_id ?? '', name: p.name ?? p.where, kind: p.kind === 'health' ? 'health' : 'switch' }) }} />
              ))}
            </Stack>
          )}
          {!!data.attention?.length && (
            <section aria-labelledby="needs-attention">
              <Title order={2} size="h4" id="needs-attention">{t('problems.attention.title')}</Title>
              <Text size="sm" c="dimmed" mb="xs">{t('problems.attention.text')}</Text>
              <Stack gap="xs">
                {data.attention.map((p) => <Row key={p.id} p={p} canMute={false} busy={false} onMute={() => {}} />)}
              </Stack>
            </section>
          )}
          {data.mutes.length > 0 && (
            <section aria-labelledby="muted-switches">
              <Title order={2} size="h4" id="muted-switches" mb="xs">{t('problems.mutes')}</Title>
              <Stack gap={4}>
                {data.mutes.map((m) => (
                  <Group key={m.switch_id} gap="sm">
                    <Text size="sm"><Anchor href={m.kind === 'health' ? '/health' : `/plan?switch=${encodeURIComponent(m.name)}`}>{m.name}</Anchor> · {t('problems.mutedUntil', { time: clock(m.until), who: m.by ?? '?' })}{m.reason ? ` · ${m.reason}` : ''}</Text>
                    {m.until - now < ENDING_SOON && (
                      <Badge color="warn" variant="light" tt="none">
                        {t('problems.endsIn', { count: Math.max(1, Math.ceil((m.until - now) / 60)) })}
                      </Badge>
                    )}
                    {data.can_mute && (
                      <Group gap={4}>
                        <Button size="compact-xs" variant="subtle" onClick={() => extend.mutate(m.switch_id)} disabled={extend.isPending}
                          aria-label={t('problems.extendLabel', { name: m.name })}>
                          {t('problems.extend')}
                        </Button>
                        <Button size="compact-xs" variant="subtle" onClick={() => unmute.mutate(m.switch_id)} disabled={unmute.isPending}>
                          {t('problems.unmute')}
                        </Button>
                      </Group>
                    )}
                  </Group>
                ))}
              </Stack>
            </section>
          )}
        </Stack>
      )}
      <MuteDialog target={target} busy={mute.isPending} error={dialogError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </Layout>
  )
}
