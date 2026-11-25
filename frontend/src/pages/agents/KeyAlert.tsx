import { Button, Code, CopyButton, Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { OneTimeSecret } from '@bitsandbricks/ui'
import { runCommand } from './runCommand'

/** ``image`` is the agent image tagged with the version this Floorbit is tested with (from the server). */
export type Made = { name: string; key: string; image?: string; rotated?: boolean }

/** A key just made (enrolled or "New key"): shown this once (the shared OneTimeSecret), with the
 *  command that starts the agent. */
export function KeyAlert({ made, onClose }: { made: Made; onClose: () => void }) {
  const { t } = useTranslation()
  const run = runCommand(made, window.location.origin)
  const insecure = window.location.protocol === 'http:'
  return (
    <OneTimeSecret secret={made.key} label={t('agents.keyLabel')} onDone={onClose}
      title={t(made.rotated ? 'agents.rotatedTitle' : 'agents.madeTitle', { name: made.name })}>
      <Stack gap="xs">
        <Text size="sm">{t(made.rotated ? 'agents.rotatedHelp' : 'agents.madeHelp')}</Text>
        <Text size="sm" fw={600} mt="xs">{t('agents.runTitle')}</Text>
        <Code block style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{run}</Code>
        {insecure && <Text size="sm" className="fb-tone-warn">{t('agents.runInsecure')}</Text>}
        <Group>
          <CopyButton value={run}>
            {({ copied, copy }) => (
              <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('agents.copied') : t('agents.copyRun')}</Button>
            )}
          </CopyButton>
        </Group>
      </Stack>
    </OneTimeSecret>
  )
}
