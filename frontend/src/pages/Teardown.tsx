import { ActionIcon, Alert, Anchor, Badge, Button, Checkbox, Group, Loader, Paper, Progress, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconDownload, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useFeature } from '@/api/queries'
import type { Teardown as TeardownData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { when } from './handover/format'

function Part({ title, done, left, children }: { title: string; done: boolean; left: number; children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb="xs">
        <Title order={2} size="h4">{title}</Title>
        <Badge variant="light" color={done ? 'up' : 'warn'} tt="none">{done ? t('teardown.partDone') : t('teardown.left', { count: left })}</Badge>
      </Group>
      {children}
    </Paper>
  )
}

/** After the event: gear back, configs archived, data exported, and the team's own steps. */
export default function Teardown() {
  const { t, i18n } = useTranslation()
  const gearOn = useFeature('gear')
  const qc = useQueryClient()
  const canExport = useCan('settings.manage')
  const query = useQuery({ queryKey: qk.teardown, queryFn: () => get<TeardownData>('/api/teardown') })
  const set = (d: TeardownData) => qc.setQueryData(qk.teardown, d)
  useLiveEvent('teardown.changed', () => void qc.invalidateQueries({ queryKey: qk.teardown }))
  useLiveEvent('gear.changed', () => void qc.invalidateQueries({ queryKey: qk.teardown }))
  const [text, setText] = useState('')
  const tickSwitch = useMutation({ mutationFn: (v: { id: string; done: boolean }) => put<TeardownData>(`/api/teardown/switches/${v.id}`, { done: v.done }), onSuccess: set })
  const tickItem = useMutation({ mutationFn: (v: { id: string; done: boolean }) => patch<TeardownData>(`/api/teardown/items/${v.id}`, { done: v.done }), onSuccess: set })
  const addItem = useMutation({ mutationFn: () => post<TeardownData>('/api/teardown/items', { text: text.trim() }), onSuccess: (d) => { set(d); setText('') } })
  const removeItem = useMutation({ mutationFn: (id: string) => del<TeardownData>(`/api/teardown/items/${id}`), onSuccess: set })
  const error = query.error ?? tickSwitch.error ?? tickItem.error ?? addItem.error ?? removeItem.error
  const d = query.data
  const exportUrl = `/api/teardown/export.zip?lang=${i18n.language.startsWith('de') ? 'de' : 'en'}&tz=${new Date().getTimezoneOffset()}`

  return (
    <Layout title={t('teardown.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('teardown.title')} desc={t('teardown.intro')} />
      <Stack gap="md">
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Group justify="space-between" mb={6}>
                <Title order={2} size="h3">{d.done ? t('teardown.allDone') : t('teardown.stillLeft', { count: d.left })}</Title>
                <Text size="sm" c="dimmed">{t('teardown.progress', { done: d.total - d.left, total: d.total })}</Text>
              </Group>
              <Progress value={d.total ? ((d.total - d.left) / d.total) * 100 : 100} color={d.done ? 'up' : 'bit'} size="lg" radius="xl"
                aria-label={t('teardown.progress', { done: d.total - d.left, total: d.total })} />
            </Paper>

            <Part title={t('teardown.gear')} done={d.parts.gear.done} left={d.parts.gear.left}>
              {d.parts.gear.out.length === 0 ? <Text size="sm" c="dimmed">{t('teardown.gearBack')}</Text> : (
                <Stack gap={4}>
                  {d.parts.gear.out.map((g) => (
                    <Text key={g.id} size="sm"><b>{g.name}</b> · {t('teardown.with', { to: g.to, when: when(g.at) })}</Text>
                  ))}
                  {gearOn && (
                    <Anchor href="/gear" size="sm" mt={4}>{t('teardown.openGear')}</Anchor>
                  )}
                </Stack>
              )}
            </Part>

            <Part title={t('teardown.configs')} done={d.parts.configs.done} left={d.parts.configs.left}>
              <Text size="sm" c="dimmed" mb="xs">{t('teardown.configsHelp')}</Text>
              {d.parts.configs.switches.length === 0 ? <Text size="sm" c="dimmed">{t('teardown.noSwitches')}</Text> : (
                <Stack gap={6}>
                  {d.parts.configs.switches.map((s) => (
                    <Checkbox key={s.id} checked={!!s.archived} onChange={(e) => tickSwitch.mutate({ id: s.id, done: e.currentTarget.checked })}
                      label={s.name} description={s.archived ? t('teardown.doneBy', { who: s.archived.by ?? '?', when: when(s.archived.at) }) : undefined} />
                  ))}
                </Stack>
              )}
            </Part>

            <Part title={t('teardown.export')} done={d.parts.export.done} left={d.parts.export.left}>
              <Text size="sm" c="dimmed" mb="xs">{t('teardown.exportHelp')}</Text>
              {d.parts.export.last && <Text size="sm" mb="xs">{t('teardown.exportedBy', { who: d.parts.export.last.by ?? '?', when: when(d.parts.export.last.at) })}</Text>}
              {canExport ? (
                <Button component="a" href={exportUrl} leftSection={<IconDownload size={16} />}
                  onClick={() => window.setTimeout(() => void qc.invalidateQueries({ queryKey: qk.teardown }), 1500)}>
                  {t('teardown.download')}
                </Button>
              ) : <Text size="sm">{t('teardown.adminOnly')}</Text>}
            </Part>

            <Part title={t('teardown.custom')} done={d.parts.custom.done} left={d.parts.custom.left}>
              <Stack gap={6}>
                {d.parts.custom.items.map((i) => (
                  <Group key={i.id} justify="space-between" wrap="nowrap">
                    <Checkbox checked={!!i.done_at} onChange={(e) => tickItem.mutate({ id: i.id, done: e.currentTarget.checked })}
                      label={i.text} description={i.done_at ? t('teardown.doneBy', { who: i.done_by ?? '?', when: when(i.done_at) }) : undefined} />
                    <ActionIcon variant="subtle" color="gray" aria-label={t('teardown.remove', { text: i.text })} onClick={() => removeItem.mutate(i.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                ))}
                <Group gap="xs" mt="xs" wrap="nowrap">
                  <TextInput aria-label={t('teardown.newStep')} placeholder={t('teardown.newStepPlaceholder')} value={text} maxLength={200}
                    onChange={(e) => setText(e.currentTarget.value)} style={{ flex: 1 }}
                    onKeyDown={(e) => { if (e.key === 'Enter' && text.trim()) addItem.mutate() }} />
                  <Button variant="default" disabled={!text.trim()} loading={addItem.isPending} onClick={() => addItem.mutate()}>{t('teardown.add')}</Button>
                </Group>
              </Stack>
            </Part>
          </>
        )}
      </Stack>
    </Layout>
  )
}
