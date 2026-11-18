import { Alert, Anchor, Badge, Button, Group, Stack, Table, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconCloudUpload, IconDownload, IconLock, IconRestore } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { Panel } from '@/components/ui'
import { ago, dateTime } from '@/lib/time'
import { bytes } from '@/pages/traffic/format'
import { TestLine } from './editor'
import type { TestResult } from './model'

type Run = { at: number; by?: string; ok: boolean; name?: string; size?: number; error?: string }
type Listed = { key: string; name: string; size: number; made: string; encrypted: boolean }
export type S3Overview = {
  configured: boolean; interval_hours: number; keep: number; bucket?: string; prefix?: string; encrypted?: boolean
  last?: Run; last_ok?: Run; backups: Listed[]; error?: string
}

const KEY = ['settings', 'backup', 's3'] as const

/** Backups in an S3 bucket: when the last one went up, back up now, and restore or download a listed one. */
export function S3BackupPanel() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: KEY, queryFn: () => get<S3Overview>('/api/settings/backup/s3') })
  const [result, setResult] = useState<TestResult | null>(null)
  const [pending, setPending] = useState<Listed | null>(null)
  const upload = useMutation({
    mutationFn: () => post<{ name: string; size: number; removed: string[] }>('/api/settings/backup/s3'),
    onSuccess: (r) => {
      setResult({ ok: true, message: t('settings.s3.uploaded', { size: bytes(r.size) }) + (r.removed.length ? ' ' + t('settings.s3.removed', { count: r.removed.length }) : '') })
      void qc.invalidateQueries({ queryKey: KEY })
    },
    onError: (e) => { setResult({ ok: false, message: (e as Error).message }); void qc.invalidateQueries({ queryKey: KEY }) },
  })
  const restore = useMutation({
    mutationFn: (key: string) => post<{ kept?: string[] }>('/api/settings/backup/s3/restore', { key }),
    onSuccess: (r) => {
      setPending(null)
      setResult({ ok: true, message: t('settings.backup.restored') + (r.kept?.length ? ' ' + t('settings.backup.kept') : '') })
      // Settings and the theme come from the server with the page, so load it again.
      setTimeout(() => window.location.reload(), r.kept?.length ? 6000 : 1200)
    },
    onError: (e) => { setPending(null); setResult({ ok: false, message: (e as Error).message }) },
  })
  const d = query.data
  const schedule = d && (d.interval_hours > 0 ? t('settings.s3.every', { count: d.interval_hours }) : t('settings.s3.manual'))

  return (
    <Panel title={t('settings.s3.title')} desc={t('settings.s3.desc')}
      actions={d?.configured ? (
        <Button size="xs" leftSection={<IconCloudUpload size={16} />} loading={upload.isPending} onClick={() => { setResult(null); upload.mutate() }}>
          {t('settings.s3.now')}
        </Button>
      ) : undefined}>
      {query.isPending && <Text size="sm" c="dimmed">{t('common.loading')}</Text>}
      {d && !d.configured && (
        <Text size="sm">{t('settings.s3.off')} <Anchor href="/settings/backup">{t('settings.s3.setUp')}</Anchor></Text>
      )}
      {d?.configured && (
        <Stack gap="sm">
          <Group gap="xs">
            <Badge variant="light" color="gray">{d.bucket}/{d.prefix}</Badge>
            <Badge variant="light" color={d.encrypted ? 'up' : 'warn'} leftSection={d.encrypted ? <IconLock size={12} /> : undefined}>
              {t(d.encrypted ? 'settings.s3.encrypted' : 'settings.s3.notEncrypted')}
            </Badge>
            <Text size="sm" c="dimmed">{schedule} · {t('settings.s3.keep', { count: d.keep })}</Text>
          </Group>
          {d.last && (
            <Text size="sm" c={d.last.ok ? undefined : 'down'}>
              {d.last.ok
                ? t('settings.s3.lastOk', { when: ago(d.last.at * 1000), by: d.last.by })
                : t('settings.s3.lastFailed', { when: ago(d.last.at * 1000), error: d.last.error })}
            </Text>
          )}
          {d.error && <Alert color="down" variant="light">{d.error}</Alert>}
          {d.backups.length > 0 ? (
            <Table.ScrollContainer minWidth={420}>
              <Table verticalSpacing={6} fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('settings.s3.made')}</Table.Th>
                    <Table.Th>{t('settings.s3.size')}</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {d.backups.map((b) => (
                    <Table.Tr key={b.key}>
                      <Table.Td>
                        {dateTime(new Date(b.made))}
                        {b.encrypted && <IconLock size={12} style={{ marginLeft: 6, verticalAlign: -1 }} aria-label={t('settings.s3.encrypted')} />}
                      </Table.Td>
                      <Table.Td>{bytes(b.size)}</Table.Td>
                      <Table.Td>
                        <Group gap={4} justify="flex-end" wrap="nowrap">
                          <Button size="compact-xs" variant="subtle" component="a" leftSection={<IconDownload size={14} />}
                            href={`/api/settings/backup/s3/download?key=${encodeURIComponent(b.key)}`} download>
                            {t('settings.s3.download')}
                          </Button>
                          <Button size="compact-xs" variant="subtle" color="down" leftSection={<IconRestore size={14} />}
                            onClick={() => { setResult(null); setPending(b) }}>
                            {t('settings.s3.restore')}
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          ) : !d.error && <Text size="sm" c="dimmed">{t('settings.s3.none')}</Text>}
          {pending && (
            <Alert color="warn" variant="light" role="alertdialog" aria-label={t('settings.s3.restore')}>
              <Text size="sm" mb="sm">{t('settings.s3.confirm', { when: dateTime(new Date(pending.made)) })}</Text>
              <Group gap="sm">
                <Button color="down" loading={restore.isPending} onClick={() => restore.mutate(pending.key)}>{t('settings.backup.go')}</Button>
                <Button variant="default" onClick={() => setPending(null)}>{t('common.cancel')}</Button>
              </Group>
            </Alert>
          )}
        </Stack>
      )}
      {result && <Stack mt="sm"><TestLine result={result} /></Stack>}
    </Panel>
  )
}
