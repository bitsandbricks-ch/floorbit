import { Alert, Button, Code, CopyButton, Group, Stack, Table, Text } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import type { LibreNMSAlertsSetup as Setup } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Panel } from '@/components/ui'

function Copy({ value }: { value: string }) {
  const { t } = useTranslation()
  return (
    <CopyButton value={value} timeout={2000}>
      {({ copied, copy }) => (
        <Button size="compact-xs" variant="subtle" onClick={copy}>{copied ? t('plugins.librenmsAlerts.copied') : t('plugins.librenmsAlerts.copy')}</Button>
      )}
    </CopyButton>
  )
}

/** What to paste into LibreNMS's API transport (issue #951). Behind a button: showing it shows the
 *  token, which the server writes to the audit log. */
export function LibreNMSAlertsSetup() {
  const { t } = useTranslation()
  const [setup, setSetup] = useState<Setup | null>(null)
  const show = useMutation({ mutationFn: () => get<Setup>('/api/alerts/librenms/setup'), onSuccess: setSetup })
  const renew = useMutation({
    mutationFn: () => post<{ token: string }>('/api/alerts/librenms/token'),
    onSuccess: (r) => setSetup((s) => (s ? { ...s, token: r.token } : s)),
  })
  const error = show.error ?? renew.error
  return (
    <Panel title={t('plugins.librenmsAlerts.title')} desc={t('plugins.librenmsAlerts.desc')}>
      <Stack gap="sm">
        {!setup ? (
          <Group><Button variant="default" loading={show.isPending} onClick={() => show.mutate()}>{t('plugins.librenmsAlerts.show')}</Button></Group>
        ) : (
          <>
            {!setup.port && <Alert color="warn">{t('plugins.librenmsAlerts.off')}</Alert>}
            {!setup.agents.length && <Alert color="warn">{t('plugins.librenmsAlerts.noAgent')}</Alert>}
            <Table withRowBorders={false} verticalSpacing={4}>
              <Table.Tbody>
                <Table.Tr><Table.Th>{t('plugins.librenmsAlerts.method')}</Table.Th><Table.Td><Code>{setup.method}</Code></Table.Td></Table.Tr>
                {setup.agents.map((a) => (
                  <Table.Tr key={a.id}>
                    <Table.Th>{t('plugins.librenmsAlerts.url', { agent: a.name })}</Table.Th>
                    <Table.Td>
                      <Group gap={6}><Code style={{ overflowWrap: 'anywhere' }}>{a.url}</Code><Copy value={a.url} /></Group>
                      {!a.address_known && <Text size="xs" c="dimmed">{t('plugins.librenmsAlerts.addressUnknown')}</Text>}
                    </Table.Td>
                  </Table.Tr>
                ))}
                <Table.Tr><Table.Th>{t('plugins.librenmsAlerts.headers')}</Table.Th><Table.Td><Code>Content-Type={setup.content_type}</Code></Table.Td></Table.Tr>
                <Table.Tr>
                  <Table.Th>{t('plugins.librenmsAlerts.token')}</Table.Th>
                  <Table.Td><Group gap={6}><Code>{setup.token}</Code><Copy value={setup.token} />
                    <ConfirmButton variant="subtle" danger size="compact-xs" label={t('plugins.librenmsAlerts.newToken')}
                      question={t('plugins.librenmsAlerts.newTokenQuestion')} onConfirm={() => renew.mutate()} />
                  </Group></Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
            <Group justify="space-between"><Text size="sm" fw={600}>{t('plugins.librenmsAlerts.body')}</Text><Copy value={setup.body} /></Group>
            <Code block>{setup.body}</Code>
            <Text size="sm" c="dimmed">{t('plugins.librenmsAlerts.after', { count: setup.active })}</Text>
          </>
        )}
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
      </Stack>
    </Panel>
  )
}
