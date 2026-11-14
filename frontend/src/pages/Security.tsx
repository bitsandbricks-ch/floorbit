import { Alert, Badge, Button, Group, Loader, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { IconPlugConnectedX, IconRefresh } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useSecurity } from '@/api/queries'
import type { Finding, SecurityList, Severity } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { PortDialog, type PortRequest } from './security/PortDialog'

const TONE: Record<Severity, string> = { high: 'down', medium: 'warn', low: 'gray' }

function ago(ts: number, t: (k: string, o?: Record<string, unknown>) => string) {
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60))
  if (mins < 1) return t('security.justNow')
  if (mins < 60) return t('security.minutesAgo', { count: mins })
  return t('security.hoursAgo', { count: Math.round(mins / 60) })
}

function where(f: { switch: string; port: string; seat?: string | null }, t: (k: string, o?: Record<string, unknown>) => string) {
  const port = [f.switch, f.port].filter(Boolean).join(' · ')
  return f.seat ? `${t('security.seat', { seat: f.seat })} (${port})` : port
}

function FindingCard({ f, list, busy, onShut, onAck }: {
  f: Finding
  list: SecurityList
  busy: boolean
  onShut: () => void
  onAck: (on: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" className={`fb-finding ${f.severity}`} aria-label={f.title} component="article">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4} style={{ minWidth: 0 }}>
          <Group gap="xs">
            <Badge color={TONE[f.severity]} variant="filled">{t(`security.severity.${f.severity}`)}</Badge>
            <Badge variant="light" color="gray">{t(`security.kind.${f.kind}`)}</Badge>
            {f.ack && <Badge variant="outline" color="up">{t('security.onIt', { who: f.ack.by ?? '?' })}</Badge>}
          </Group>
          <Text fw={600}>{f.title}</Text>
          {(f.switch || f.seat) && <Text size="sm">{where(f, t)}</Text>}
          {f.detail && <Text size="sm" c="dimmed">{f.detail}</Text>}
          {f.evidence.length > 0 && (
            <ul className="fb-evidence">
              {f.evidence.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
          <Text size="xs" c="dimmed">
            {t('security.seen', { first: ago(f.first_seen, t), plugin: f.plugin_name })}
          </Text>
        </Stack>
        <Stack gap="xs" style={{ flexShrink: 0 }}>
          {list.can_act && f.switch && f.port && (
            <Button size="xs" color="down" leftSection={<IconPlugConnectedX size={14} />} onClick={onShut} disabled={busy}>
              {t('security.shut')}
            </Button>
          )}
          <Button size="xs" variant="default" onClick={() => onAck(!f.ack)} disabled={busy}>
            {f.ack ? t('security.unack') : t('security.ack')}
          </Button>
        </Stack>
      </Group>
    </Paper>
  )
}

/** Security findings from the security plugins, with one-click port shutdown. */
export default function Security() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useSecurity()
  const canCheck = useCan('plugins.run')
  const [request, setRequest] = useState<PortRequest | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [matchSeat, setMatchSeat] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const refresh = () => void client.invalidateQueries({ queryKey: qk.security })
  useLiveEvent('security.finding', refresh)

  const check = useMutation({
    mutationFn: () => post<SecurityList>('/api/security/check'),
    onSuccess: (data) => client.setQueryData(qk.security, data),
  })
  const ack = useMutation({
    mutationFn: (v: { id: string; on: boolean }) => post<Finding>(`/api/security/${encodeURIComponent(v.id)}/ack`, { on: v.on }),
    onSuccess: refresh,
  })
  const port = useMutation({
    mutationFn: (v: { request: PortRequest; extra: Record<string, string | boolean | undefined> }) => {
      const { action, finding, switch: sw, port: p } = v.request
      return post<{ message: string }>(`/api/ports/${action}`, finding ? { finding, ...v.extra } : { switch: sw, port: p, ...v.extra })
    },
    onSuccess: (r) => {
      setRequest(null)
      setMatchSeat(null)
      setMessage(r.message)
      refresh()
    },
    onError: (e) => {
      // A match seat (issue #31): ask a second time instead of failing.
      const zone = e instanceof ApiError && typeof e.data.match_seat === 'string' ? e.data.match_seat : null
      setMatchSeat(zone)
      setDialogError(zone ? null : e.message)
    },
  })
  const error = list.error ?? check.error ?? ack.error
  const data = list.data

  return (
    <Layout title={t('security.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('security.title')}
        desc={t('security.intro')}
        actions={canCheck && (
          <Button leftSection={<IconRefresh size={16} />} loading={check.isPending} onClick={() => check.mutate()}>
            {t('security.checkNow')}
          </Button>
        )}
      />
      {error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: error.message })}</Alert>}
      {message && <Alert color="up" mb="md" withCloseButton onClose={() => setMessage(null)}>{message}</Alert>}
      {list.isPending || !data ? (
        <Loader size="sm" />
      ) : (
        <Stack gap="lg">
          <section aria-labelledby="sec-active">
            <Title order={2} size="h4" id="sec-active" mb="xs">{t('security.active', { count: data.findings.length })}</Title>
            {!data.findings.length ? (
              <Text c="dimmed">{data.plugins ? t('security.none') : t('security.noPlugins')}</Text>
            ) : (
              <Stack gap="sm">
                {data.findings.map((f) => (
                  <FindingCard key={f.id} f={f} list={data} busy={ack.isPending || port.isPending}
                    onAck={(on) => ack.mutate({ id: f.id, on })}
                    onShut={() => { setDialogError(null); setRequest({ action: 'shutdown', finding: f.id, where: where(f, t) }) }} />
                ))}
              </Stack>
            )}
          </section>

          {data.shut_ports.length > 0 && (
            <section aria-labelledby="sec-shut">
              <Title order={2} size="h4" id="sec-shut" mb="xs">{t('security.shutPorts')}</Title>
              <Table.ScrollContainer minWidth={560}>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('security.port')}</Table.Th>
                      <Table.Th>{t('security.why')}</Table.Th>
                      <Table.Th>{t('security.by')}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.shut_ports.map((p) => (
                      <Table.Tr key={`${p.switch} ${p.port}`}>
                        <Table.Td>{where(p, t)}</Table.Td>
                        <Table.Td>{p.reason || '—'}</Table.Td>
                        <Table.Td>{p.by}, {ago(p.at, t)}</Table.Td>
                        <Table.Td>
                          {data.can_act && (
                            <Button size="xs" variant="default"
                              onClick={() => { setDialogError(null); setRequest({ action: 'enable', switch: p.switch, port: p.port, where: where(p, t) }) }}>
                              {t('security.enable')}
                            </Button>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </section>
          )}

          {data.cleared.length > 0 && (
            <section aria-labelledby="sec-cleared">
              <Title order={2} size="h4" id="sec-cleared" mb="xs">{t('security.cleared')}</Title>
              <Stack gap={4}>
                {data.cleared.map((f) => (
                  <Text key={`${f.id}-${f.cleared_at}`} size="sm" c="dimmed">
                    {t(`security.kind.${f.kind}`)}: {f.title} · {where(f, t)} · {t('security.clearedAgo', { ago: ago(f.cleared_at ?? f.last_seen, t) })}
                  </Text>
                ))}
              </Stack>
            </section>
          )}
        </Stack>
      )}
      <PortDialog request={request} needsLogin={!!data?.needs_login} busy={port.isPending} error={dialogError} matchSeat={matchSeat}
        onClose={() => { setRequest(null); setMatchSeat(null) }}
        onConfirm={(extra) => request && port.mutate({ request, extra })} />
    </Layout>
  )
}
