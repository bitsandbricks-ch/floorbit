import { Alert, Anchor, Badge, Button, Group, Loader, Modal, Paper, Select, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconBellOff } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useProblems } from '@/api/queries'
import type { Problem } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const MINUTES = ['30', '60', '240', '720', '1440']
type T = (k: string, o?: Record<string, unknown>) => string

function ago(ts: number, t: T) {
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60))
  if (mins < 1) return t('problems.justNow')
  if (mins < 60) return t('problems.minutesAgo', { count: mins })
  return t('problems.hoursAgo', { count: Math.round(mins / 60) })
}

const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

function Row({ p, canMute, busy, onMute }: { p: Problem; canMute: boolean; busy: boolean; onMute: () => void }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="md" p="sm" component="article" aria-label={p.title}
      className={`fb-problem ${p.muted ? 'muted' : p.level}`}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Stack gap={2} style={{ minWidth: 0 }}>
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
        <Group gap="xs" wrap="nowrap">
          {p.since && <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('problems.since', { ago: ago(p.since, t) })}</Text>}
          {p.link && <Button size="xs" variant="default" component="a" href={p.link}>{t('problems.open')}</Button>}
          {canMute && p.kind === 'switch' && !p.muted && (
            <Button size="xs" variant="subtle" leftSection={<IconBellOff size={14} />} onClick={onMute} disabled={busy}>{t('problems.mute')}</Button>
          )}
        </Group>
      </Group>
    </Paper>
  )
}

function MuteDialog({ target, busy, error, onClose, onSave }: {
  target: { id: string; name: string } | null
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (minutes: number, reason: string) => void
}) {
  const { t } = useTranslation()
  return (
    <Modal opened={!!target} onClose={onClose} title={t('problems.muteTitle', { name: target?.name })}>
      <MuteForm busy={busy} error={error} onClose={onClose} onSave={onSave} />
    </Modal>
  )
}

function MuteForm({ busy, error, onClose, onSave }: {
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
        <Text size="sm">{t('problems.muteText')}</Text>
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

/** Everything wrong right now, in one list, with mutes for switches someone is working on (issue #10). */
export default function Problems() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useProblems()
  const [target, setTarget] = useState<{ id: string; name: string } | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const refresh = () => void client.invalidateQueries({ queryKey: qk.problems })
  useLiveEvent('monitor.poll', refresh)
  useLiveEvent('alerts.changed', refresh)
  useLiveEvent('power.changed', refresh)
  useLiveEvent('attention.changed', refresh)

  const mute = useMutation({
    mutationFn: (v: { id: string; minutes: number; reason: string }) =>
      post('/api/alerts/mutes', { switch_id: v.id, minutes: v.minutes, reason: v.reason }),
    onSuccess: () => { setTarget(null); refresh() },
    onError: (e) => setDialogError(e.message),
  })
  const unmute = useMutation({
    mutationFn: (id: string) => del(`/api/alerts/mutes/${encodeURIComponent(id)}`),
    onSuccess: refresh,
  })
  const data = list.data
  const error = list.error ?? unmute.error

  return (
    <Layout title={t('problems.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('problems.title')} desc={t('problems.intro')} />
      {error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: error.message })}</Alert>}
      {list.isPending || !data ? (
        <Loader size="sm" />
      ) : (
        <Stack gap="md">
          {data.quiet_hours && <Alert color="gray" variant="light">{t('problems.quiet')}</Alert>}
          <Group gap="xs" aria-live="polite">
            {(['down', 'warn', 'muted'] as const).filter((k) => data.counts[k]).map((k) => (
              <Badge key={k} size="lg" tt="none" color={k === 'down' ? 'down' : k === 'warn' ? 'warn' : 'gray'}
                variant={k === 'muted' ? 'light' : 'filled'}>
                {t(`problems.count.${k}`, { count: data.counts[k] })}
              </Badge>
            ))}
          </Group>
          {!data.problems.length ? (
            <Text c="dimmed">{t('problems.none')}</Text>
          ) : (
            <Stack gap="xs">
              {data.problems.map((p) => (
                <Row key={p.id} p={p} canMute={data.can_mute} busy={mute.isPending}
                  onMute={() => { setDialogError(null); setTarget({ id: p.switch_id ?? '', name: p.where }) }} />
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
                    <Text size="sm"><Anchor href="/">{m.name}</Anchor> · {t('problems.mutedUntil', { time: clock(m.until), who: m.by ?? '?' })}{m.reason ? ` · ${m.reason}` : ''}</Text>
                    {data.can_mute && (
                      <Button size="compact-xs" variant="subtle" onClick={() => unmute.mutate(m.switch_id)} disabled={unmute.isPending}>
                        {t('problems.unmute')}
                      </Button>
                    )}
                  </Group>
                ))}
              </Stack>
            </section>
          )}
        </Stack>
      )}
      <MuteDialog target={target} busy={mute.isPending} error={dialogError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ id: target.id, minutes, reason })} />
    </Layout>
  )
}
