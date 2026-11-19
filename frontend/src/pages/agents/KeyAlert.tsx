import { Alert, Button, Code, CopyButton, Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

export type Made = { name: string; key: string; rotated?: boolean }

function Copy({ value }: { value: string }) {
  const { t } = useTranslation()
  return (
    <CopyButton value={value}>
      {({ copied, copy }) => (
        <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('agents.copied') : t('agents.copy')}</Button>
      )}
    </CopyButton>
  )
}

/** A key just made (enrolled or "New key"): shown this once, with the command that starts the agent. */
export function KeyAlert({ made, onClose }: { made: Made; onClose: () => void }) {
  const { t } = useTranslation()
  const run = [
    'docker run -d --restart on-failure:3 --name floorbit-agent \\',
    `  -e FLOORBIT_URL=${window.location.origin} \\`,
    `  -e FLOORBIT_AGENT_KEY=${made.key} \\`,
    '  ghcr.io/bitsandbricks-ch/floorbit-agent',
  ].join('\n')
  return (
    <Alert color="up" role="status" withCloseButton onClose={onClose} title={t(made.rotated ? 'agents.rotatedTitle' : 'agents.madeTitle', { name: made.name })}>
      <Stack gap="xs">
        <Text size="sm">{t(made.rotated ? 'agents.rotatedHelp' : 'agents.madeHelp')}</Text>
        <Group gap="xs" wrap="nowrap">
          <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{made.key}</Code>
          <Copy value={made.key} />
        </Group>
        <Text size="sm" fw={600} mt="xs">{t('agents.runTitle')}</Text>
        <Code block style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{run}</Code>
        <Group><Copy value={run} /></Group>
      </Stack>
    </Alert>
  )
}
