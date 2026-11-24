import { Alert, Button, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { TAKES, useTakeDrift, type DriftRow } from '@/api/inventoryDrift'
import { DataTable } from '@/components/DataTable'
import { ago } from '@/lib/time'

/** Where the inventory and the device disagree (issue #918), with the device's value one click away
 *  for fields and the management address. Shown only while there is something. */
export function DriftPanel({ deviceId, rows, canEdit }: { deviceId: string; rows: DriftRow[]; canEdit: boolean }) {
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
    <>
      <Text size="sm" c="dimmed" mb="xs">{t('inventoryDrift.intro')}</Text>
      {take.error && <Alert color="down" role="alert" mb="xs">{take.error.message}</Alert>}
      {take.isSuccess && <Text size="sm" role="status" className="fb-tone-ok" mb="xs">✓ {t('inventoryDrift.taken')}</Text>}
      <DataTable label={t('inventoryDrift.title')} rows={rows} rowKey={(r) => `${r.kind}:${r.field}`} urlState={false} pageSize={0} bare cards
        columns={[
          { id: 'what', header: t('inventoryDrift.col.what'), card: 'inline', cell: (r) => (
            <>
              <Text size="sm">{what(r)}</Text>
              {r.kind === 'hostname' && <Text size="xs" c="dimmed">{t('inventoryDrift.hostnameHint')}</Text>}
            </>
          ) },
          { id: 'inventory', header: t('inventoryDrift.col.inventory'), card: 'label', wrap: true,
            cell: (r) => <Text size="sm" ff="monospace">{value(r, r.configured)}</Text> },
          { id: 'device', header: t('inventoryDrift.col.device'), card: 'label', wrap: true,
            cell: (r) => <Text size="sm" ff="monospace" c="warn">{value(r, r.actual)}</Text> },
          { id: 'since', header: t('inventoryDrift.col.since'), card: 'label',
            cell: (r) => <Text size="xs" c="dimmed">{r.since ? ago(Date.parse(r.since) / 1000, i18n.language) : '–'}</Text> },
          ...(canEdit ? [{ id: 'take', header: null, cell: (r: DriftRow) => TAKES.includes(r.kind) && (
            <Button size="compact-sm" variant="default" aria-label={t('inventoryDrift.takeLabel', { what: what(r) })}
              loading={take.isPending && take.variables === r.field} onClick={() => take.mutate(r.field)}>
              {t('inventoryDrift.take')}
            </Button>
          ) }] : []),
        ]} />
    </>
  )
}
