import { Alert, Badge, Button, Group, Stack, Text } from '@mantine/core'
import { IconPlugConnectedX, IconTerminal2 } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Finding } from '@/api/types'
import { Panel } from '@/components/ui'
import { ago } from '@/lib/time'
import { pluginName } from '@/lib/pluginName'
import { PortDialog, type PortRequest } from '@/pages/security/PortDialog'
import { findingWhere } from './findingWhere'

const TONE = { high: 'down', medium: 'warn', low: 'gray' } as const

export type PageFinding = Omit<Finding, 'title' | 'cleared_at'>

/** A security finding on its problem's page (issue #885): what the plugin saw, and shutting its
 *  port (or the switch terminal where the port is an uplink). */
export function FindingPanel({ f, canShut, needsLogin }: { f: PageFinding; canShut: boolean; needsLogin: boolean }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [request, setRequest] = useState<PortRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const shut = useMutation({
    mutationFn: (extra: Record<string, string | undefined>) => post<{ message: string }>('/api/ports/shutdown', { finding: f.id, ...extra }),
    onSuccess: (r) => {
      setRequest(null)
      setDone(r.message)
      void client.invalidateQueries({ queryKey: qk.problems })
      void client.invalidateQueries({ queryKey: qk.security })
    },
    onError: (e) => setError(e.message),
  })
  const onPort = !!(f.switch && f.port)
  return (
    <Panel title={t('problem.finding.title')}
      actions={<>
        {canShut && onPort && !f.uplink && (
          <Button size="xs" color="down" leftSection={<IconPlugConnectedX size={14} />}
            onClick={() => { setError(null); setRequest({ action: 'shutdown', finding: f.id, where: findingWhere(f, t) }) }}>
            {t('security.shut')}
          </Button>
        )}
        {onPort && f.uplink && (
          <Button size="xs" variant="default" leftSection={<IconTerminal2 size={14} />}
            component={Link} to={`/terminal?switch=${encodeURIComponent(f.switch)}`}>
            {t('security.openSwitch')}
          </Button>
        )}
      </>}>
      <Stack gap={6}>
        <Group gap="xs">
          <Badge color={TONE[f.severity]} variant="filled">{t(`security.severity.${f.severity}`)}</Badge>
          <Badge variant="light" color="gray">{t(`security.kind.${f.kind}`)}</Badge>
        </Group>
        {f.detail && <Text size="sm">{f.detail}</Text>}
        {(f.mac || f.ip) && (
          <Text size="sm" ff="monospace">{[f.mac, f.ip].filter(Boolean).join(' · ')}</Text>
        )}
        {f.evidence.length > 0 && (
          <>
            <Text size="sm" c="dimmed">{t('problem.finding.evidence')}</Text>
            <ul className="fb-evidence">{f.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
          </>
        )}
        {onPort && f.uplink && <Text size="sm">{t(`security.uplink.${f.uplink}`)}</Text>}
        <Text size="xs" c="dimmed">
          {t('security.seen', { first: ago(f.first_seen), plugin: pluginName(t, f.plugin, f.plugin_name) })}
        </Text>
        {done && <Alert color="up" withCloseButton onClose={() => setDone(null)}>{done}</Alert>}
      </Stack>
      <PortDialog request={request} needsLogin={needsLogin} busy={shut.isPending} error={error}
        onClose={() => setRequest(null)} onConfirm={(extra) => shut.mutate(extra)} />
    </Panel>
  )
}
