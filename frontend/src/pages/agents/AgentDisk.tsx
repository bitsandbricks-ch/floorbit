import { Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { AgentDisk } from '@/api/agentDisk'
import { PanelField, UsageBar } from '@bitsandbricks/ui'
import { bytes } from '@/pages/traffic/format'

/** What the agent keeps on its disk against its one budget (floorbit/disk_budget.py, #1485).
 *  A full budget is normal: the oldest data makes room, so the bar never turns red. */
export function DiskBudget({ disk }: { disk?: AgentDisk }) {
  const { t, i18n } = useTranslation()
  if (!disk) return null
  const share = disk.budget ? Math.min(100, Math.round(((disk.used ?? 0) / disk.budget) * 100)) : null
  const hours = (h?: number) => (h ?? 0).toLocaleString(i18n.language, { maximumFractionDigits: 1 })
  const kinds = Object.entries(disk.kinds).sort(([, a], [, b]) => (b.bytes ?? 0) - (a.bytes ?? 0))
  return (
    <Stack gap="sm">
      <PanelField label={disk.auto ? t('agents.disk.budgetAuto') : t('agents.disk.budget')}>
        {t('agents.disk.used', { used: bytes(disk.used), budget: disk.budget ? bytes(disk.budget) : '–' })}
      </PanelField>
      <UsageBar value={share} label={t('agents.disk.budget')} warnAt={101} errAt={101} />
      {kinds.map(([name, k]) => (
        <PanelField key={name} label={t(`agents.disk.kind.${name}`, { defaultValue: name })}>
          {t('agents.disk.kindValue', { size: bytes(k.bytes), hours: hours(k.hours) })}
          {k.dropped ? <Text span size="xs" c="dimmed">{' · '}{t('agents.disk.dropped', { count: k.dropped })}</Text> : null}
        </PanelField>
      ))}
      {kinds.length === 0 && <Text size="sm" c="dimmed">{t('agents.disk.empty')}</Text>}
    </Stack>
  )
}
