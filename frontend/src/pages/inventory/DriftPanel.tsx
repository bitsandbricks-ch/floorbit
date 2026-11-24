import { Alert, Anchor, Badge, Button, Group, Stack, Text, VisuallyHidden } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { TAKES, useTakeDrift, type DriftDevice, type DriftRow } from '@/api/inventoryDrift'
import { ago } from '@/lib/time'
import { devicePath } from './model'
import './DriftPanel.css'

/** The hunk groups in the order a diff lists its files: fields, then name and address, then interfaces. */
const GROUPS: { id: string; kinds: DriftRow['kind'][] }[] = [
  { id: 'fields', kinds: ['field'] },
  { id: 'identity', kinds: ['hostname', 'address'] },
  { id: 'interfaces', kinds: ['interface'] },
]

/** Where the inventory and the device disagree (issues #918, #903), shown like a code diff: one hunk per
 *  row, the inventory's value as the removed line and the device's as the added one. The device's value
 *  is one click away for fields and the management address. */
export function DriftPanel({ deviceId, rows, canEdit, intro = true }: {
  deviceId: string; rows: DriftRow[]; canEdit: boolean; intro?: boolean
}) {
  const { t, i18n } = useTranslation()
  const take = useTakeDrift(deviceId)
  const what = (r: DriftRow) => {
    if (r.kind === 'field') return t(`inventory.field.${r.field}`, { defaultValue: r.field })
    if (r.kind === 'interface') return t('inventoryDrift.kind.interface', { name: r.field })
    return t(`inventoryDrift.kind.${r.kind}`)
  }
  const value = (r: DriftRow, v: DriftRow['configured']) =>
    r.kind === 'interface' && typeof v === 'string' && ['present', 'missing', 'hidden'].includes(v)
      ? t(`inventoryDrift.value.${v}`) : String(v ?? '–')
  return (
    <Stack gap="sm">
      {intro && <Text size="sm" c="dimmed">{t('inventoryDrift.intro')}</Text>}
      {take.error && <Alert color="down" role="alert">{take.error.message}</Alert>}
      {take.isSuccess && <Text size="sm" role="status" className="fb-tone-ok">✓ {t('inventoryDrift.taken')}</Text>}
      {GROUPS.map((g) => {
        const hunks = rows.filter((r) => g.kinds.includes(r.kind))
        if (!hunks.length) return null
        return (
          <section key={g.id} className="fb-diff-file" aria-label={t(`inventoryDrift.group.${g.id}`)}>
            <Text className="fb-diff-file-head" size="xs" fw={600}>{t(`inventoryDrift.group.${g.id}`)} · {hunks.length}</Text>
            {hunks.map((r) => (
              <div key={`${r.kind}:${r.field}`} className="fb-diff-hunk" role="group" aria-label={what(r)}>
                <Group className="fb-diff-hunk-head" gap="xs" justify="space-between" wrap="nowrap">
                  <Text size="xs" ff="monospace" truncate>
                    @@ {what(r)}{r.since && <Text span size="xs" c="dimmed"> · {t('inventoryDrift.since', { when: ago(Date.parse(r.since) / 1000, i18n.language) })}</Text>}
                  </Text>
                  {canEdit && TAKES.includes(r.kind) && (
                    <Button size="compact-xs" variant="default" aria-label={t('inventoryDrift.takeLabel', { what: what(r) })}
                      loading={take.isPending && take.variables === r.field} onClick={() => take.mutate(r.field)}>
                      {t('inventoryDrift.take')}
                    </Button>
                  )}
                </Group>
                <div className="fb-diff-line is-del">
                  <span aria-hidden="true">-</span>
                  <VisuallyHidden component="span">{t('inventoryDrift.col.inventory')}: </VisuallyHidden>{value(r, r.configured)}
                </div>
                <div className="fb-diff-line is-add">
                  <span aria-hidden="true">+</span>
                  <VisuallyHidden component="span">{t('inventoryDrift.col.device')}: </VisuallyHidden>{value(r, r.actual)}
                </div>
                {r.kind === 'hostname' && <Text size="xs" c="dimmed" px="xs" py={4}>{t('inventoryDrift.hostnameHint')}</Text>}
              </div>
            ))}
          </section>
        )
      })}
    </Stack>
  )
}

/** Every device that differs, one block per device like the files of a multi-file diff. */
export function DriftAll({ devices, canEdit }: { devices: DriftDevice[]; canEdit: boolean }) {
  const { t } = useTranslation()
  if (!devices.length) return <Text c="dimmed">{t('inventoryDrift.none')}</Text>
  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">{t('inventoryDrift.intro')}</Text>
      {devices.map((d) => (
        <Stack key={d.id} gap="xs">
          <Group gap="xs">
            <Anchor component={Link} to={devicePath(d.id)} fw={600}>{d.name}</Anchor>
            <Badge size="sm" variant="light" color="warn" tt="none">{t('inventoryDrift.count', { count: d.drift.length })}</Badge>
          </Group>
          <DriftPanel deviceId={d.id} rows={d.drift} canEdit={canEdit} intro={false} />
        </Stack>
      ))}
    </Stack>
  )
}
