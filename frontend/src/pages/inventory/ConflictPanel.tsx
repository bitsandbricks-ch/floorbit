import { Alert, Anchor, Button, Group, Stack, Text, VisuallyHidden } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { readsPath, usePickDeciding, useTakeConflict, type SourceConflict } from '@/api/discoverySources'
import { useCan } from '@/api/queries'
import { ago } from '@/lib/time'
import './DriftPanel.css'

/** Where two discovery sources read different values for one field (issue #965), shown next to drift
 *  like a diff hunk: the deciding source's value as the removed line, the other's as the added one. */
export function ConflictPanel({ deviceId, role, rows, canEdit }: {
  deviceId: string; role: string; rows: SourceConflict[]; canEdit: boolean
}) {
  const { t, i18n } = useTranslation()
  const take = useTakeConflict(deviceId)
  const pick = usePickDeciding()
  const canPick = useCan('settings.manage')
  const kind = t(`inventory.role.${role}`, { defaultValue: role })
  const error = take.error ?? pick.error
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">{t('discoverySources.conflictIntro')}</Text>
      {error && <Alert color="down" role="alert">{error.message}</Alert>}
      <section className="fb-diff-file" aria-label={t('discoverySources.conflictTitle')}>
        {rows.map((r) => {
          const field = t(`inventory.field.${r.field}`, { defaultValue: r.field })
          return (
            <div key={`${r.field}:${r.other.source}`} className="fb-diff-hunk" role="group" aria-label={field}>
              <Group className="fb-diff-hunk-head" gap="xs" wrap="nowrap">
                <Text size="xs" ff="monospace" truncate>
                  @@ system.{r.field}{r.since && <Text span size="xs" c="dimmed"> · {t('inventoryDrift.since', { when: ago(Date.parse(r.since) / 1000, i18n.language) })}</Text>}
                </Text>
              </Group>
              <div className="fb-diff-line is-del">
                <span aria-hidden="true">-</span>
                <VisuallyHidden component="span">{t('discoverySources.deciding')}: </VisuallyHidden>
                {String(r.deciding.value)} <Text span size="xs" c="dimmed">({t('discoverySources.decidingSource', { name: r.deciding.name })})</Text>
              </div>
              <div className="fb-diff-line is-add">
                <span aria-hidden="true">+</span>
                <VisuallyHidden component="span">{t('discoverySources.other')}: </VisuallyHidden>
                {String(r.other.value)} <Text span size="xs" c="dimmed">({r.other.name})</Text>
              </div>
              {(canEdit || canPick) && (
                <Group gap="xs" px="xs" py={6}>
                  {canEdit && (
                    <Button size="compact-xs" loading={take.isPending && take.variables?.field === r.field}
                      onClick={() => take.mutate({ field: r.field, source: r.other.source })}>
                      {t('discoverySources.take', { name: r.other.name })}
                    </Button>
                  )}
                  {canPick && (
                    <Button size="compact-xs" variant="default" loading={pick.isPending}
                      onClick={() => pick.mutate({ role, area: 'identity', source: r.other.source })}>
                      {t('discoverySources.makeDecide', { name: r.other.name, kind })}
                    </Button>
                  )}
                </Group>
              )}
            </div>
          )
        })}
      </section>
      <Anchor component={Link} to={readsPath(role)} size="sm">{t('discoverySources.whatReads', { kind })}</Anchor>
    </Stack>
  )
}
