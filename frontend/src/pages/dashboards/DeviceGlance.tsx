import { ActionIcon, Anchor, Badge, Group, Loader, Stack, Text, Title } from '@mantine/core'
import { IconX } from '@tabler/icons-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { devicePath } from '../inventory/model'
import { useDeviceDetail } from '../inventory/scope'

/** The picked row's device beside a large widget (#925): what it is, what is wired to it and what
 *  goes down with it, and the ways into its page. Esc closes it before it closes the large widget. */
export function DeviceGlance({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation()
  const q = useDeviceDetail(id)
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); onClose() } }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  }, [onClose])
  const d = q.data
  const wired = d?.connected
  const wiredParts = wired ? ([['cables', wired.cables.length], ['circuits', wired.circuits.length], ['uplinks', wired.uplinks.length]] as const)
    .filter(([, n]) => n > 0).map(([k, n]) => t(`dashboards.glance.${k}`, { count: n })) : []
  const page = devicePath(id)
  return (
    <aside className="fb-glance" aria-label={d?.name || id}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div style={{ minWidth: 0 }}>
          <Title order={3} fz="lg" className="fb-glance-name">{d?.name || id}</Title>
          {d && <Text size="sm" c="dimmed">{[d.role, d.model, d.mgmt_ip].filter(Boolean).join(' · ')}</Text>}
        </div>
        <ActionIcon variant="subtle" color="gray" onClick={onClose} aria-label={t('dashboards.glance.close')}><IconX size={16} /></ActionIcon>
      </Group>
      {q.isPending && <Loader size="sm" aria-label={t('common.loading')} />}
      {q.error && <Text size="sm" c="dimmed">{t('dashboards.glance.noDetail')}</Text>}
      {d && (
        <Stack gap={6}>
          {(d.location || d.hall) && <Text size="sm">{[...new Set([d.hall, d.location].filter(Boolean))].join(' · ')}</Text>}
          <Text size="sm">{t('dashboards.glance.ports', { count: d.interfaces.filter((i) => !i.hidden).length })}</Text>
          {wiredParts.length > 0 && <Text size="sm">{t('dashboards.glance.wired', { what: wiredParts.join(', ') })}</Text>}
          {!!d.runs_here?.length && (
            <div>
              <Text size="sm" fw={700}>{t('dashboards.glance.runsHere')}</Text>
              <Group gap={4}>{d.runs_here.map((r) => <Badge key={`${r.kind}.${r.id}`} variant="light" size="sm">{r.name}</Badge>)}</Group>
            </div>
          )}
          {d.notes && <Text size="sm" c="dimmed" lineClamp={3}>{d.notes}</Text>}
        </Stack>
      )}
      <Stack gap={4} mt="xs">
        <Anchor component={Link} to={page} fw={700}>{t('dashboards.glance.open')}</Anchor>
        <Anchor component={Link} to={`${page}?tab=interfaces`}>{t('dashboards.glance.portsTab')}</Anchor>
        <Anchor component={Link} to={`${page}?tab=telemetry`}>{t('dashboards.glance.telemetryTab')}</Anchor>
      </Stack>
    </aside>
  )
}
