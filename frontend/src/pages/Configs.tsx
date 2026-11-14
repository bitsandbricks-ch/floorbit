import {
  Alert, Anchor, Badge, Button, Code, Grid, Group, Loader, MultiSelect, Paper, PasswordInput, ScrollArea, SimpleGrid, Stack,
  Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconDownload, IconFlag, IconRefresh } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { ConfigBackupResult, ConfigDiff, ConfigHistory, ConfigOverview, ConfigRow } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { when } from './handover/format'

/** Switch config backups and what changed during the event (issue #96). Backups run with the
 *  tech's own switch login, which lives only in this page's state for one run. */
export default function Configs() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selected = params.get('switch')
  const query = useQuery({ queryKey: qk.configs, queryFn: () => get<ConfigOverview>('/api/configs') })
  const [switches, setSwitches] = useState<string[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const backup = useMutation({
    mutationFn: (body: Record<string, unknown>) => post<{ results: ConfigBackupResult[] }>('/api/configs/backup', body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.configs }),
  })
  const info = query.data
  const ready = switches.length > 0 && (!info?.needs_login || (username.trim() !== '' && password !== ''))
  const submit = () => {
    const body: Record<string, unknown> = { switches }
    if (info?.needs_login) Object.assign(body, { username: username.trim(), password })
    setPassword('')
    backup.mutate(body)
  }
  const failed = backup.data?.results.filter((r) => !r.ok) ?? []
  const open = (sw: string | null) => setParams(sw ? { switch: sw } : {})

  return (
    <Layout title={t('configs.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('configs.title')} desc={t('configs.intro', { keep: info?.keep ?? 50 })} />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : info && (
          <>
            {!info.available ? <Alert color="warn">{t('configs.noPlugin')}</Alert> : (
              <Paper withBorder radius="lg" p="md">
                <form autoComplete="off" onSubmit={(e) => { e.preventDefault(); submit() }}>
                  <Stack gap="sm">
                    <SimpleGrid cols={{ base: 1, sm: info.needs_login ? 3 : 1 }}>
                      <MultiSelect label={t('configs.switches')} value={switches} onChange={setSwitches} searchable
                        data={info.switches.map((r) => r.switch)} maxValues={info.max_switches}
                        placeholder={switches.length ? undefined : t('configs.pick', { count: info.max_switches })} />
                      {info.needs_login && (
                        <>
                          <TextInput label={t('configs.username')} value={username} maxLength={64} autoComplete="off"
                            onChange={(e) => setUsername(e.currentTarget.value)} />
                          <PasswordInput label={t('configs.password')} value={password} maxLength={256} autoComplete="off"
                            description={t('configs.passwordHint')} onChange={(e) => setPassword(e.currentTarget.value)} />
                        </>
                      )}
                    </SimpleGrid>
                    {backup.error && <Alert color="down" role="alert">{backup.error.message}</Alert>}
                    {backup.data && (
                      <Alert color={failed.length ? 'warn' : 'up'}>
                        {t('configs.done', { count: backup.data.results.length - failed.length,
                          changed: backup.data.results.filter((r) => r.changed).length })}
                        {failed.map((r) => <Text key={r.switch} size="sm">{r.switch}: {r.error}</Text>)}
                      </Alert>
                    )}
                    <Group justify="space-between" wrap="wrap">
                      <Group gap="xs">
                        <Button size="xs" variant="subtle" onClick={() => setSwitches(info.switches.map((r) => r.switch).slice(0, info.max_switches))}>
                          {t('configs.all', { count: Math.min(info.switches.length, info.max_switches) })}
                        </Button>
                        <Button size="xs" variant="subtle" onClick={() => setSwitches(info.switches.filter((r) => !r.last).map((r) => r.switch).slice(0, info.max_switches))}>
                          {t('configs.missing')}
                        </Button>
                      </Group>
                      <Button type="submit" disabled={!ready} loading={backup.isPending} leftSection={<IconRefresh size={16} />}>
                        {switches.length ? t('configs.backup', { count: switches.length }) : t('configs.backupNone')}
                      </Button>
                    </Group>
                  </Stack>
                </form>
              </Paper>
            )}
            {selected ? <Detail sw={selected} onBack={() => open(null)} /> : <Overview rows={info.switches} onOpen={open} />}
          </>
        )}
      </Stack>
    </Layout>
  )
}

function State({ row }: { row: ConfigRow }) {
  const { t } = useTranslation()
  if (!row.last) return <Badge variant="light" color="gray" tt="none" miw="max-content">{t('configs.none')}</Badge>
  return row.changed
    ? <Badge variant="light" color="warn" tt="none" miw="max-content">{t('configs.changed')}</Badge>
    : <Badge variant="light" color="up" tt="none" miw="max-content">{t('configs.same')}</Badge>
}

function Overview({ rows, onOpen }: { rows: ConfigRow[]; onOpen: (sw: string) => void }) {
  const { t } = useTranslation()
  const changed = rows.filter((r) => r.changed).length
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb="xs">
        <Title order={2} size="h4">{t('configs.overview')}</Title>
        <Text size="sm" c="dimmed">{t('configs.summary', { changed, total: rows.length })}</Text>
      </Group>
      <ScrollArea type="auto">
        <Table striped highlightOnHover miw={560}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('configs.switch')}</Table.Th>
              <Table.Th>{t('configs.state')}</Table.Th>
              <Table.Th>{t('configs.lastCopy')}</Table.Th>
              <Table.Th>{t('configs.lastChecked')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.switch}>
                <Table.Td style={{ whiteSpace: 'nowrap' }}>
                  {r.last
                    ? <Anchor component="button" ff="monospace" onClick={() => onOpen(r.switch)}>{r.switch}</Anchor>
                    : <Text ff="monospace" span>{r.switch}</Text>}
                </Table.Td>
                <Table.Td><State row={r} /></Table.Td>
                <Table.Td>{r.last ? t('configs.byWhen', { when: when(r.last.at), by: r.last.by }) : '—'}</Table.Td>
                <Table.Td>{r.checked ? t('configs.byWhen', { when: when(r.checked.at), by: r.checked.by }) : '—'}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Paper>
  )
}

function Detail({ sw, onBack }: { sw: string; onBack: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const enc = encodeURIComponent(sw)
  const history = useQuery({ queryKey: qk.configHistory(sw), queryFn: () => get<ConfigHistory>(`/api/configs/${enc}`) })
  const diff = useQuery({
    queryKey: qk.configDiff(sw, from, to),
    queryFn: () => get<ConfigDiff>(`/api/configs/${enc}/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
    enabled: (history.data?.copies.length ?? 0) > 0,
  })
  const baseline = useMutation({
    mutationFn: (id: string) => post(`/api/configs/${enc}/baseline`, { id }),
    onSuccess: () => {
      setFrom('')
      void qc.invalidateQueries({ queryKey: qk.configs })
    },
  })
  const h = history.data
  const d = diff.data
  return (
    <Grid>
      <Grid.Col span={{ base: 12, lg: 4 }}>
      <Paper withBorder radius="lg" p="md">
        <Group justify="space-between" mb="xs" wrap="nowrap">
          <Title order={2} size="h4" ff="monospace">{sw}</Title>
          <Button size="xs" variant="default" onClick={onBack}>{t('configs.allSwitches')}</Button>
        </Group>
        {history.isPending ? <Loader size="sm" /> : (
          <Stack gap={8}>
            {h?.copies.map((c) => {
              const isBase = c.id === h.baseline
              return (
                <Paper key={c.id} withBorder radius="md" p="xs">
                  <Group justify="space-between" wrap="nowrap" gap={6}>
                    <div>
                      <Text size="sm" fw={600}>{when(c.at)}</Text>
                      <Text size="xs" c="dimmed">{t('configs.copyMeta', { by: c.by, count: c.lines })}</Text>
                    </div>
                    <Group gap={4} wrap="nowrap">
                      {isBase && <Badge size="sm" variant="light" tt="none" miw="max-content">{t('configs.baseline')}</Badge>}
                      <Button size="compact-xs" variant="subtle" onClick={() => { setFrom(h.baseline ?? ''); setTo(c.id) }}>
                        {t('configs.compare')}
                      </Button>
                      {!isBase && (
                        <Button size="compact-xs" variant="subtle" leftSection={<IconFlag size={12} />}
                          loading={baseline.isPending && baseline.variables === c.id} onClick={() => baseline.mutate(c.id)}>
                          {t('configs.makeBaseline')}
                        </Button>
                      )}
                      <Button size="compact-xs" variant="subtle" component="a" aria-label={t('configs.download')}
                        href={`/api/configs/${enc}/${encodeURIComponent(c.id)}?download=1`}>
                        <IconDownload size={14} />
                      </Button>
                    </Group>
                  </Group>
                </Paper>
              )
            })}
          </Stack>
        )}
      </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 8 }}>
      <Paper withBorder radius="lg" p="md">
        {diff.isPending ? <Loader size="sm" /> : d && (
          <Stack gap="xs">
            <Group justify="space-between" wrap="wrap">
              <Text fw={600}>{t('configs.diffTitle', { from: when(d.from.at), to: when(d.to.at) })}</Text>
              <Group gap={6}>
                <Badge variant="light" color="up" tt="none">+{d.added}</Badge>
                <Badge variant="light" color="down" tt="none">−{d.removed}</Badge>
              </Group>
            </Group>
            {d.lines.length === 0 ? <Text c="dimmed">{t('configs.noChange')}</Text> : (
              <ScrollArea.Autosize mah={620} type="auto">
                <Code block fz="xs" style={{ whiteSpace: 'pre' }}>
                  {d.lines.map((ln, i) => {
                    const head = ln.startsWith('+++') || ln.startsWith('---')
                    const color = head ? undefined : ln.startsWith('+') ? 'var(--mantine-color-up-text, green)'
                      : ln.startsWith('-') ? 'var(--mantine-color-down-text, red)' : ln.startsWith('@@') ? 'var(--mantine-color-dimmed)' : undefined
                    return <div key={i} style={{ color, fontWeight: head ? 700 : undefined }}>{ln || ' '}</div>
                  })}
                </Code>
              </ScrollArea.Autosize>
            )}
          </Stack>
        )}
      </Paper>
      </Grid.Col>
    </Grid>
  )
}
