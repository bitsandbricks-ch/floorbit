import { Anchor, Badge, Button, CloseButton, Group, Paper, SimpleGrid, Stack, TagsInput, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { del, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { HealthCheck } from '@/api/types'
import type { ServiceTags } from '@/api/serviceChecks'
import type { ServiceRowData } from '@/widgets/serviceRows'
import { clock } from '@/lib/time'
import { Sparkline } from '@bitsandbricks/ui'
import { CacheMachine } from '../lancache/LancacheView'

const MUTE_MINUTES = 60

/** One service's details beside the list (issue #1337, layout A): what Service health showed (its
 *  numbers, the "full in" forecast, since when, muted until) and what can be done with it. */
export function ServicePanel({ row, check, allTags, canEdit, canMute, canRcon, onConsole, onClose }: {
  row: ServiceRowData; check: HealthCheck | undefined; allTags: string[]
  canEdit: boolean; canMute: boolean; canRcon: boolean; onConsole: () => void; onClose: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const tags = row.tags ?? []
  const showTags = (id: string, next: string[]) => qc.setQueryData(qk.serviceSummary, (old: { tags?: ServiceTags } | undefined) =>
    old ? { ...old, tags: { ...old.tags, [id]: next } } : old)
  const saveTags = useMutation({
    mutationFn: (next: string[]) => post<{ id: string; tags: string[] }>('/api/services/tags', { id: row.sid, tags: next }),
    // Shown at once; the server's cleaned list (trimmed, no doubles) replaces it.
    onMutate: (next) => showTags(row.sid, next),
    onSuccess: (got) => showTags(got.id, got.tags),
    onError: () => void qc.invalidateQueries({ queryKey: qk.serviceSummary }),
  })
  const done = () => {
    void qc.invalidateQueries({ queryKey: qk.health })
    void qc.invalidateQueries({ queryKey: qk.serviceSummary })
  }
  const mute = useMutation({ mutationFn: () => post('/api/alerts/mutes', { service_id: row.sid, minutes: MUTE_MINUTES }), onSuccess: done })
  const unmute = useMutation({ mutationFn: () => del(`/api/alerts/mutes/${encodeURIComponent(`health:${row.sid}`)}`), onSuccess: done })
  const error = saveTags.error ?? mute.error ?? unmute.error
  // The server sends muted_until only while the mute runs.
  const muted = check?.muted_until ?? null
  const forecast = check?.forecast?.full_in_min
  return (
    <Paper withBorder p="md" className="fb-service-panel" component="aside" aria-label={t('services.panel.label', { name: row.name })}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <div style={{ minWidth: 0 }}>
            <Group gap={8} wrap="nowrap">
              <span className={`fb-bit ${row.status === 'up' ? '' : row.status === 'unknown' ? 'is-off' : `is-${row.status}`}`} aria-hidden="true" />
              <Title order={2} size="h4" style={{ overflowWrap: 'anywhere' }}>{row.name}</Title>
            </Group>
            <Text size="sm" c="dimmed">{t(`services.types.${row.type}`)} · <span style={{ fontFamily: 'var(--mantine-font-family-monospace)' }}>{row.target}</span></Text>
          </div>
          <CloseButton aria-label={t('services.panel.close')} onClick={onClose} />
        </Group>
        <Group gap="xs">
          <Badge variant="light" color={row.status === 'up' ? 'up' : row.status === 'unknown' ? 'gray' : row.status}>{t(`services.status.${row.status}`)}</Badge>
          {check?.since && <Text size="sm" c="dimmed">{t('services.panel.since', { time: clock(check.since) })}</Text>}
        </Group>
        {(check?.summary || row.note) && <Text size="sm">{check?.summary || row.note}</Text>}
        {forecast != null && forecast <= 180 && (
          <Text size="sm" c={check?.forecast?.raised ? 'warn' : undefined}>
            {t('services.panel.fullIn', { count: forecast, rate: check?.forecast?.rate_per_min })}
          </Text>
        )}
        {!!check?.metrics.length && (
          <SimpleGrid cols={3} spacing="xs">
            {check.metrics.map((m) => (
              <Paper key={m.label} withBorder p="xs">
                <Text fw={700} ff="monospace" c={m.tone === 'warn' ? 'warn' : m.tone === 'err' ? 'down' : undefined}>
                  {m.value}{m.unit && <Text span size="xs" c="dimmed"> {m.unit}</Text>}
                </Text>
                <Text size="xs" c="dimmed">{m.label}</Text>
              </Paper>
            ))}
          </SimpleGrid>
        )}
        {row.points.length > 1 && (
          <div style={{ height: 64 }} aria-label={t('services.panel.history')} role="img"><Sparkline points={row.points} min={0} /></div>
        )}
        {row.elsewhere && <Text size="sm" c="dimmed">{row.elsewhere}</Text>}
        {row.type === 'lancache' && (
          <>
            <CacheMachine />
            <Anchor component={Link} to="/games" size="sm">{t('services.panel.downloads')}</Anchor>
          </>
        )}
        {canEdit ? (
          <TagsInput label={t('services.panel.tags')} description={t('services.panel.tagsHelp')} data={allTags} value={tags}
            maxTags={8} clearable onChange={(next) => saveTags.mutate(next)} />
        ) : !!tags.length && (
          <Group gap={6}>{tags.map((tag) => <Badge key={tag} variant="outline" color="gray" tt="none">{tag}</Badge>)}</Group>
        )}
        {muted && <Text size="sm" c="dimmed">{t('services.panel.mutedUntil', { time: clock(muted) })}</Text>}
        {error && <Text size="sm" c="down" role="alert">{error.message}</Text>}
        <Group gap="xs">
          {row.edit && <Button size="compact-md" variant="default" onClick={row.edit}>{t('services.edit')}</Button>}
          {row.game && canRcon && (
            <Button size="compact-md" variant="default" disabled={!row.game.rcon} onClick={onConsole}>{t('gameServers.console')}</Button>
          )}
          {check && canMute && (muted
            ? <Button size="compact-md" variant="default" loading={unmute.isPending} onClick={() => unmute.mutate()}>{t('services.panel.unmute')}</Button>
            : <Button size="compact-md" variant="default" loading={mute.isPending} onClick={() => mute.mutate()}>{t('services.panel.mute')}</Button>)}
          <Anchor component={Link} to="/problems" size="sm">{t('services.panel.problems')}</Anchor>
        </Group>
      </Stack>
    </Paper>
  )
}
