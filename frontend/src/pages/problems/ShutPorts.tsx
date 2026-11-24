import { Alert, Button, Group, Text } from '@mantine/core'
import { IconRefresh } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useSecurity } from '@/api/queries'
import type { SecurityList } from '@/api/types'
import { DataTable } from '@/components/DataTable'
import { Panel } from '@/components/ui'
import { ErrorBanner } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'
import { PortDialog, type PortRequest } from '@/pages/security/PortDialog'
import { findingWhere } from './findingWhere'

/** Under the security problems (issue #885): the ports Floorbit shut, to turn on again, and asking
 *  the security plugins now. What the Security page had besides its findings. Shown with the
 *  security filter (``always``), and otherwise while a port is shut. */
export function ShutPorts({ always }: { always: boolean }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useSecurity()
  const canCheck = useCan('plugins.run')
  const [request, setRequest] = useState<PortRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const refresh = () => {
    void client.invalidateQueries({ queryKey: qk.security })
    void client.invalidateQueries({ queryKey: qk.problems })
  }
  const check = useMutation({
    mutationFn: () => post<SecurityList>('/api/security/check'),
    onSuccess: (data) => { client.setQueryData(qk.security, data); void client.invalidateQueries({ queryKey: qk.problems }) },
  })
  const enable = useMutation({
    mutationFn: (v: { request: PortRequest; extra: Record<string, string | undefined> }) =>
      post<{ message: string }>('/api/ports/enable', { switch: v.request.switch, port: v.request.port, ...v.extra }),
    onSuccess: (r) => { setRequest(null); setDone(r.message); refresh() },
    onError: (e) => setError(e.message),
  })
  const data = list.data
  if (!data) return <ErrorBanner error={list.error} />
  // Outside the security filter only while a port is still shut: it stays down until someone acts.
  if (!always && !data.shut_ports.length) return null
  return (
    <Panel title={t('security.shutPorts')}
      desc={data.plugins ? undefined : t('problem.shut.noPlugins')}
      actions={canCheck && (
        <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} loading={check.isPending} onClick={() => check.mutate()}>
          {t('security.checkNow')}
        </Button>
      )}>
      <ErrorBanner error={check.error} mb="sm" />
      {done && <Alert color="up" mb="sm" withCloseButton onClose={() => setDone(null)}>{done}</Alert>}
      {data.shut_ports.length === 0 ? <Text size="sm" c="dimmed">{t('problem.shut.none')}</Text> : (
        <DataTable label={t('security.shutPorts')} rows={data.shut_ports} rowKey={(p) => `${p.switch} ${p.port}`}
          defaultSort={{ id: 'when', desc: true }} minWidth={560} urlState={false} pageSize={0}
          columns={[
            { id: 'port', header: t('security.port'), sort: (p) => `${p.switch} ${p.port}`, cell: (p) => findingWhere(p, t) },
            { id: 'why', header: t('security.why'), wrap: true, cell: (p) => p.reason || '—' },
            { id: 'when', header: t('security.by'), sort: (p) => p.at, cell: (p) => `${p.by}, ${ago(p.at)}` },
            { id: 'act', header: null, cell: (p) => data.can_act && (
              <Group justify="flex-end">
                <Button size="xs" variant="default"
                  onClick={() => { setError(null); setRequest({ action: 'enable', switch: p.switch, port: p.port, where: findingWhere(p, t) }) }}>
                  {t('security.enable')}
                </Button>
              </Group>
            ) },
          ]} />
      )}
      <PortDialog request={request} needsLogin={data.needs_login} busy={enable.isPending} error={error}
        onClose={() => setRequest(null)} onConfirm={(extra) => request && enable.mutate({ request, extra })} />
    </Panel>
  )
}
