import { Alert, Badge, Select, Stack, Text } from '@mantine/core'
import { IconRadar } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { readsPath, usePickDeciding, useReads, type ReadsRow } from '@/api/discoverySources'
import { useCan } from '@/api/queries'
import { ItemPage } from '@/components/ItemPage'
import { DataTable, type DataColumn } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'

const ROLES = ['switch', 'router', 'firewall', 'access-point', 'server', 'vm', 'pdu', 'other']
const DEFAULT = '__default__'

/** "What Floorbit reads from a firewall" (issue #965): per area, the source that decides, the others
 *  that read it too, how often, where it goes, the last run and the open conflicts. Admins pick
 *  another deciding source per kind of device. /inventory/reads/<role>. */
export default function ReadsPage() {
  const { t, i18n } = useTranslation()
  const role = useParams().role ?? 'switch'
  const navigate = useNavigate()
  const reads = useReads(role)
  const pick = usePickDeciding()
  const canPick = useCan('settings.manage')
  const kind = t(`inventory.role.${role}`, { defaultValue: role })
  const source = (r: ReadsRow, id: string | null) => r.sources.find((s) => s.id === id)?.name ?? '–'

  const columns: DataColumn<ReadsRow>[] = [
    { id: 'area', header: t('discoverySources.col.area'), sort: (r) => r.name, cell: (r) => (
      <>
        <Text size="sm" fw={500} span>{t(`discoverySources.area.${r.area}`, { defaultValue: r.name })}</Text>{' '}
        <Text size="xs" c="dimmed" span>{r.builtin ? t('discoverySources.builtIn') : source(r, r.deciding)}</Text>
      </>
    ) },
    { id: 'deciding', header: t('discoverySources.col.deciding'), wrap: true, cell: (r) => (
      <Stack gap={2}>
        {canPick && r.sources.length > 1 ? (
          <Select size="xs" w={220} allowDeselect={false} aria-label={t('discoverySources.pickLabel', { area: r.name, kind })}
            value={r.why === 'admin' ? r.deciding : DEFAULT}
            data={[{ value: DEFAULT, label: t('discoverySources.defaultOf', { name: r.sources[0].name }) },
              ...r.sources.map((s) => ({ value: s.id, label: s.name }))]}
            disabled={pick.isPending}
            onChange={(v) => pick.mutate({ role, area: r.area, source: v === DEFAULT ? null : v })} />
        ) : <Text size="sm">{source(r, r.deciding)}</Text>}
        <Text size="xs" c="dimmed">{t(`discoverySources.why.${r.why}`)}</Text>
      </Stack>
    ) },
    { id: 'also', header: t('discoverySources.col.also'), hideOnPhone: true,
      cell: (r) => r.sources.filter((s) => s.id !== r.deciding).map((s) => s.name).join(', ') || '–' },
    { id: 'every', header: t('discoverySources.col.every'), mono: true, sort: (r) => r.minutes ?? -1,
      cell: (r) => (r.minutes == null ? '–' : r.minutes === 0 ? t('discoverySources.off') : t('discoverySources.minutes', { count: r.minutes })) },
    { id: 'goes', header: t('discoverySources.col.goesTo'), hideOnPhone: true, cell: (r) => (
      r.goes_to === 'fields' || r.goes_to === 'interfaces'
        ? t(`discoverySources.goes.${r.goes_to}`)
        : <Text size="sm" ff="monospace" c="dimmed" span>{r.goes_to}</Text>
    ) },
    { id: 'last', header: t('discoverySources.col.last'), hideOnPhone: true, sort: (r) => r.last?.at ?? '',
      cell: (r) => (r.last ? (
        <Text size="sm" span c={r.last.error ? 'down' : undefined} title={r.last.error}>
          {ago(Date.parse(r.last.at) / 1000, i18n.language)}{r.last.error ? ` · ${t('discoverySources.failed')}` : ''}
        </Text>
      ) : '–') },
    { id: 'conflicts', header: t('discoverySources.col.conflicts'), sort: (r) => r.conflicts, descFirst: true,
      cell: (r) => (r.conflicts
        ? <Badge size="sm" variant="light" color="warn" tt="none">{t('discoverySources.conflicts', { count: r.conflicts })}</Badge>
        : <Text size="sm" c="dimmed" span>{t('discoverySources.noConflicts')}</Text>) },
  ]

  return (
    <ItemPage title={t('discoverySources.title', { kind })} fallbackTitle={t('inventory.title')} icon={<IconRadar size={26} />}
      back={{ href: '/inventory', label: t('inventory.page.back') }} loading={reads.isPending}
      missing={reads.error ? { title: t('inventory.page.notFound'), desc: reads.error.message } : null}
      kicker={t('discoverySources.intro')}
      actions={(
        <Select size="sm" w={200} aria-label={t('discoverySources.kind')} allowDeselect={false} value={role}
          data={ROLES.map((r) => ({ value: r, label: t(`inventory.role.${r}`) }))}
          onChange={(v) => v && navigate(readsPath(v))} />
      )}>
      <Stack gap="md">
        {pick.error && <Alert color="down" role="alert">{pick.error.message}</Alert>}
        {reads.data && !reads.data.monitoring && <Text size="sm" c="dimmed">{t('discoverySources.noMonitoring')}</Text>}
        <DataTable rows={reads.data?.rows ?? []} columns={columns} rowKey={(r) => r.area} label={t('discoverySources.title', { kind })}
          pageSize={0} urlState={false} cards minWidth={1000} empty={t('discoverySources.none')} />
      </Stack>
    </ItemPage>
  )
}
