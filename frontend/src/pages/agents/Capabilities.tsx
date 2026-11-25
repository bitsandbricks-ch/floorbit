import { Group, Stack, Text, ThemeIcon } from '@mantine/core'
import { IconCheck, IconMinus } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

/** The capabilities Floorbit knows (floorbit/agent_ha.py CAPABILITIES), in the order to show them. */
const CAPABILITIES = ['lease', 'split', 'syslog_hold', 'self_update'] as const

/** What an agent can do, and for each thing it can't, what Floorbit does instead. */
export function Capabilities({ have }: { have?: string[] }) {
  const { t } = useTranslation()
  const set = new Set(have ?? [])
  return (
    <Stack gap="xs" component="ul" style={{ listStyle: 'none', padding: 0, margin: 0 }} aria-label={t('agentCapabilities.title')}>
      {CAPABILITIES.map((c) => {
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
  )
}
