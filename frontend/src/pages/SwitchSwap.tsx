import { Alert, Anchor, Badge, Button, Group, Radio, SimpleGrid, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconDownload, IconReplace } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { ago, dateTime } from '@/lib/time'
import type { SwapEntry, SwapPlan } from './switchSwap/types'

const TYPED = 'typed'

/** A dead switch out, a spare in (issue #1060): pick the spare, give it the last config copy, patch
 *  the seats back port for port, then one click moves the serial over. The switch keeps its name and
 *  IP, so the seat mapping, cables and monitoring carry on; the dead box goes on the shelf as failed. */
export default function SwitchSwap() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const canSwap = useCan('floorplan.edit')
  const key = qk.switchSwap(id)
  const query = useQuery({ queryKey: key, queryFn: () => get<SwapPlan>(`/api/switch-swap/${encodeURIComponent(id)}`) })
  const [pick, setPick] = useState<string | null>(null)
  const [serial, setSerial] = useState('')
  const [model, setModel] = useState('')
  const [done, setDone] = useState<SwapEntry | null>(null)
  const p = query.data
  const choice = pick ?? (p?.spares[0]?.id ?? TYPED)
  const swap = useMutation({
    mutationFn: () => post<SwapPlan & { swap: SwapEntry }>(`/api/switch-swap/${encodeURIComponent(id)}`,
      choice === TYPED ? { serial, model } : { spare_id: choice }),
    onSuccess: (r) => {
      qc.setQueryData(key, r)
      setDone(r.swap); setPick(null); setSerial(''); setModel('')
      void qc.invalidateQueries({ queryKey: qk.inventoryAll })
    },
  })
  const name = p?.switch.name ?? ''
  const state = p?.switch.status === 'offline' || p?.switch.status === 'online' ? p.switch.status : 'unknown'
  const down = state === 'offline'

  return (
    <Layout title={t('switchSwap.title')} back={{ href: '/problems', label: t('switchSwap.back') }}>
      <PageHead title={name ? t('switchSwap.heading', { name }) : t('switchSwap.title')} desc={t('switchSwap.intro')} />
      <Stack gap="md">
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {query.isPending ? <LoadingState /> : p && (
          <>
            <Panel title={name} aria-label={t('switchSwap.now')}
              actions={<Badge variant="light" color={down ? 'down' : state === 'online' ? 'up' : 'gray'} tt="none" className="fb-on-tint">
                {t(`switchSwap.status.${state}`)}
                {down && p.switch.since ? ` · ${ago(p.switch.since)}` : ''}
              </Badge>}>
              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                <Fact label={t('switchSwap.model')} value={p.switch.model} />
                <Fact label={t('switchSwap.serial')} value={p.switch.serial} mono />
                <Fact label={t('switchSwap.mgmtIp')} value={p.switch.mgmt_ip} mono />
                <Fact label={t('switchSwap.incident')}
                  value={p.incident ? <Anchor href={`/incidents?q=${encodeURIComponent(`switch:${name}`)}`}>{p.incident.title}</Anchor> : ''} />
              </SimpleGrid>
              <Text size="sm" c="dimmed" mt="sm">{t('switchSwap.keeps')}</Text>
            </Panel>

            {done && (
              <Alert color="up" role="status" title={t('switchSwap.doneTitle')}>
                {t('switchSwap.done', { name, old: done.old_serial || '?', serial: done.new_serial })}
              </Alert>
            )}

            <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
              <Panel title={t('switchSwap.step1')} desc={t('switchSwap.step1Desc')}>
                <Radio.Group value={choice} onChange={setPick} aria-label={t('switchSwap.step1')}>
                  <Stack gap="xs">
                    {p.spares.map((s) => (
                      <Radio key={s.id} value={s.id} label={
                        <Group gap={6} wrap="wrap">
                          <Text size="sm" fw={600}>{s.name}</Text>
                          <Text size="sm" c="dimmed">{[s.model, s.serial].filter(Boolean).join(' · ')}</Text>
                          {s.same_model && <Badge size="xs" variant="light" color="up" tt="none" className="fb-on-tint">{t('switchSwap.sameModel')}</Badge>}
                        </Group>
                      } />
                    ))}
                    {p.spares.length === 0 && <Text size="sm" c="dimmed">{t('switchSwap.noSpares')}</Text>}
                    <Radio value={TYPED} label={t('switchSwap.typed')} />
                    {choice === TYPED && (
                      <Group grow gap="xs" align="flex-start">
                        <TextInput label={t('switchSwap.newSerial')} value={serial} onChange={(e) => setSerial(e.currentTarget.value)} required />
                        <TextInput label={t('switchSwap.newModel')} value={model} placeholder={p.switch.model}
                          onChange={(e) => setModel(e.currentTarget.value)} />
                      </Group>
                    )}
                  </Stack>
                </Radio.Group>
              </Panel>

              <Panel title={t('switchSwap.step2')} desc={t('switchSwap.step2Desc')}>
                {!p.config_readable ? <Text size="sm" c="dimmed">{t('switchSwap.configHidden')}</Text>
                  : p.config ? (
                    <Stack gap="xs" align="flex-start">
                      <Button variant="default" component="a" leftSection={<IconDownload size={16} />}
                        href={`/api/configs/${encodeURIComponent(name)}/${encodeURIComponent(p.config.id)}?download=1`}>
                        {t('switchSwap.download')}
                      </Button>
                      {p.config.at && <Text size="xs" c="dimmed">{t('switchSwap.copyFrom', { when: dateTime(p.config.at) })}</Text>}
                      <Anchor size="sm" href="/configs">{t('switchSwap.allCopies')}</Anchor>
                    </Stack>
                  ) : <Text size="sm" c="dimmed">{t('switchSwap.noCopy')} <Anchor href="/configs">{t('switchSwap.configsPage')}</Anchor></Text>}
              </Panel>

              <Panel title={t('switchSwap.step3')} desc={t('switchSwap.step3Desc', { count: p.seat_ports.length })} padding={p.seat_ports.length ? 0 : 'md'}>
                {p.seat_ports.length === 0 ? <Text size="sm" c="dimmed">{t('switchSwap.noSeats')}</Text> : (
                  <Table.ScrollContainer minWidth={200} mah={320}>
                    <Table striped stickyHeader>
                      <Table.Thead><Table.Tr><Table.Th>{t('switchSwap.port')}</Table.Th><Table.Th>{t('switchSwap.seat')}</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {p.seat_ports.map((r) => (
                          <Table.Tr key={`${r.port}-${r.seat}`}><Table.Td ff="monospace">{r.port}</Table.Td><Table.Td>{r.seat}</Table.Td></Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </Panel>
            </SimpleGrid>

            <Panel title={t('switchSwap.step4')} desc={t('switchSwap.step4Desc')}>
              <Stack gap="xs" align="flex-start">
                <ErrorBanner error={swap.error} />
                {canSwap ? (
                  <Button leftSection={<IconReplace size={16} />} loading={swap.isPending}
                    disabled={choice === TYPED && !serial.trim()} onClick={() => swap.mutate()}>
                    {t('switchSwap.swap')}
                  </Button>
                ) : <Text size="sm" c="dimmed">{t('switchSwap.noRight')}</Text>}
              </Stack>
            </Panel>

            <Panel title={t('switchSwap.history')}>
              {p.swaps.length === 0 ? <Text size="sm" c="dimmed">{t('switchSwap.noSwaps')}</Text> : (
                <Stack gap={4}>
                  {p.swaps.map((s) => (
                    <Text key={s.at} size="sm">
                      {t('switchSwap.swapLine', { when: dateTime(s.at), old: s.old_serial || '?', serial: s.new_serial, who: s.by || '?' })}
                    </Text>
                  ))}
                </Stack>
              )}
            </Panel>
          </>
        )}
      </Stack>
    </Layout>
  )
}

function Fact({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" ff={mono ? 'monospace' : undefined} style={{ overflowWrap: 'anywhere' }}>{value || '–'}</Text>
    </div>
  )
}
