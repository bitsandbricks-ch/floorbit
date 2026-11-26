import { Group, Stack, Text, ThemeIcon } from '@mantine/core'
import { IconCheck, IconMinus } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

/** The capabilities Floorbit knows (floorbit/agent_ha.py), in the order to show them: what the agent
 *  itself can do, then what its built-in plugins collect. */
const AGENT = ['lease', 'split', 'syslog_hold', 'self_update', 'syslog_ids', 'plugin_updates', 'key_roll', 'cert'] as const
const COLLECTS = ['syslog', 'netflow', 'snmp', 'traps', 'gnmi', 'mdt', 'rest', 'mac_lookup'] as const

/** What an agent can do, and for each thing it can't, what Floorbit does instead. */
export function Capabilities({ have }: { have?: string[] }) {
  const { t } = useTranslation()
  return (
    <Stack gap="sm" aria-label={t('agentCapabilities.title')}>
      <CapabilityList title={t('agentCapabilities.agent')} items={AGENT} have={have} />
      <CapabilityList title={t('agentCapabilities.collects')} items={COLLECTS} have={have} />
    </Stack>
  )
}

function CapabilityList({ title, items, have }: { title: string; items: readonly string[]; have?: string[] }) {
  const { t } = useTranslation()
  const set = new Set(have ?? [])
  return (
    <Stack gap={6}>
      <Text size="xs" fw={500} c="dimmed">{title}</Text>
      <Stack gap="xs" component="ul" style={{ listStyle: 'none', padding: 0, margin: 0 }} aria-label={title}>
        {items.map((c) => {
          const ok = set.has(c)
          return (
            <Group key={c} component="li" gap="xs" wrap="nowrap" align="flex-start">
              <ThemeIcon size={18} radius="xl" variant="light" color={ok ? 'up' : 'warn'} aria-hidden="true">
                {ok ? <IconCheck size={12} /> : <IconMinus size={12} />}
              </ThemeIcon>
              <Stack gap={0} style={{ minWidth: 0 }}>
                <Text size="sm">{t(`agentCapabilities.name.${c}`)}</Text>
                <Text size="xs" c="dimmed">{ok ? t(`agentCapabilities.yes.${c}`) : t(`agentCapabilities.no.${c}`)}</Text>
              </Stack>
            </Group>
          )
        })}
      </Stack>
    </Stack>
  )
}
