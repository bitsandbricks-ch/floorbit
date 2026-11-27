import { Badge, Button, Chip, Code, CopyButton, Group, Stack, Text } from '@mantine/core'
import { IconCheck, IconCopy } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { Card, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { dateTime } from '@/lib/time'

export type PortCheckFinding = { rule: string; label: string; ports: string[]; count: number; fix: string[]; vlan?: number }
export type PortCheck = {
  switches: { switch: string; copy: { id: string; at: number | null }; seat_ports: number; checked: number; findings: PortCheckFinding[] }[]
  no_copy: string[]
  off: string[]
  rules: { id: string; label: string; fix: string }[]
}

/** Seat ports whose config breaks a rule, read from the last config copy of each switch, with the
 *  config to paste (issue #1059). Rules the event doesn't use are turned off here. */
export function PortCheckPanel() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.portCheck, queryFn: () => get<PortCheck>('/api/configs/port-check') })
  const save = useMutation({
    mutationFn: (off: string[]) => put<PortCheck>('/api/configs/port-check', { off }),
    onSuccess: (r) => { qc.setQueryData(qk.portCheck, r); void qc.invalidateQueries({ queryKey: qk.problems }) },
  })
  const d = query.data
  const bad = d?.switches.filter((s) => s.findings.length) ?? []
  const fine = d ? d.switches.length - bad.length : 0
  return (
    <Card heading={2} id="port-check" title={t('configs.portCheck.title')} desc={t('configs.portCheck.intro')}>
      <ErrorBanner error={query.error ?? save.error} mb="sm" />
      {query.isPending ? <LoadingState rows={2} /> : d && (
        <Stack gap="md">
          <div>
            <Text size="sm" fw={600} mb={6}>{t('configs.portCheck.rules')}</Text>
            <Chip.Group multiple value={d.rules.map((r) => r.id).filter((id) => !d.off.includes(id))}
              onChange={(on) => save.mutate(d.rules.map((r) => r.id).filter((id) => !on.includes(id)))}>
              <Group gap="xs">
                {d.rules.map((r) => <Chip key={r.id} value={r.id} size="sm" disabled={save.isPending}>{r.label}</Chip>)}
              </Group>
            </Chip.Group>
          </div>
          <Text size="sm" c="dimmed">
            {t('configs.portCheck.summary', { count: d.switches.length, fine })}
            {d.no_copy.length > 0 && ` ${t('configs.portCheck.noCopy', { count: d.no_copy.length, list: d.no_copy.join(', ') })}`}
          </Text>
          {bad.map((s) => (
            <Stack key={s.switch} gap={6}>
              <Group gap="xs" justify="space-between" wrap="wrap">
                <Text fw={600} ff="monospace">{s.switch}</Text>
                <Text size="xs" c="dimmed">
                  {t('configs.portCheck.from', { when: s.copy.at ? dateTime(s.copy.at) : '?', checked: s.checked })}
                </Text>
              </Group>
              {s.findings.map((f) => (
                <Stack key={f.rule} gap={4} pl="sm" style={{ borderLeft: '3px solid var(--mantine-color-warn-filled)' }}>
                  <Group gap="xs" wrap="wrap">
                    <Badge variant="light" color="warn" tt="none" className="fb-on-tint">
                      {f.rule === 'vlan' ? t('configs.portCheck.vlan', { count: f.count, vlan: f.vlan }) : t('configs.portCheck.without', { count: f.count, rule: f.label })}
                    </Badge>
                    <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>{f.ports.join(', ')}</Text>
                  </Group>
                  <Group gap="xs" align="flex-start" wrap="nowrap">
                    <Code block style={{ flex: 1, minWidth: 0, overflowX: 'auto' }}>{f.fix.join('\n')}</Code>
                    <CopyButton value={f.fix.join('\n')} timeout={2000}>
                      {({ copied, copy }) => (
                        <Button size="xs" variant="default" onClick={copy} leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />}>
                          {copied ? t('configs.portCheck.copied') : t('configs.portCheck.copy')}
                        </Button>
                      )}
                    </CopyButton>
                  </Group>
                </Stack>
              ))}
            </Stack>
          ))}
        </Stack>
      )}
    </Card>
  )
}
