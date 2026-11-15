import {
  ActionIcon, Alert, Badge, Button, Chip, Grid, Group, Loader, NavLink, Paper, Stack, Tabs, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { IconArrowDown, IconArrowUp, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { Runbook, RunbookKind } from '@/api/types'
import { Layout } from '@/components/Layout'
import { Markdown } from '@/components/Markdown'
import { PageHead } from '@/components/PageHead'

type Draft = { title: string; kinds: RunbookKind[]; body: string }

function Editor({ book, kinds, onSaved, onCancel }: {
  book: Runbook | null; kinds: RunbookKind[]; onSaved: (id: string) => void; onCancel: () => void
}) {
  const { t } = useTranslation()
  const [d, setD] = useState<Draft>(() => book ? { title: book.title, kinds: book.kinds, body: book.body } : { title: '', kinds: [], body: '' })
  const save = useMutation({
    mutationFn: () => book ? patch<Runbook>(`/api/runbooks/${book.id}`, d) : post<Runbook>('/api/runbooks', d),
    onSuccess: (saved) => onSaved(saved.id),
  })
  return (
    <Stack gap="sm">
      <TextInput label={t('runbooks.name')} required maxLength={80} value={d.title}
        onChange={(e) => { const title = e.currentTarget.value; setD((x) => ({ ...x, title })) }} />
      <div>
        <Text size="sm" fw={500} mb={4}>{t('runbooks.for')}</Text>
        <Chip.Group multiple value={d.kinds} onChange={(v) => setD((x) => ({ ...x, kinds: v as RunbookKind[] }))}>
          <Group gap="xs">{kinds.map((k) => <Chip key={k} value={k} size="sm">{t(`runbooks.kind.${k}`)}</Chip>)}</Group>
        </Chip.Group>
      </div>
      <Tabs defaultValue="write">
        <Tabs.List>
          <Tabs.Tab value="write">{t('runbooks.write')}</Tabs.Tab>
          <Tabs.Tab value="preview">{t('runbooks.preview')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="write" pt="xs">
          <Textarea aria-label={t('runbooks.steps')} description={t('runbooks.markdownHelp')} autosize minRows={10} maxLength={20000}
            ff="monospace" value={d.body} onChange={(e) => { const body = e.currentTarget.value; setD((x) => ({ ...x, body })) }} />
        </Tabs.Panel>
        <Tabs.Panel value="preview" pt="xs"><Markdown source={d.body} /></Tabs.Panel>
      </Tabs>
      {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
      <Group gap="xs">
        <Button loading={save.isPending} disabled={!d.title.trim() || !d.body.trim()} onClick={() => save.mutate()}>{t('runbooks.save')}</Button>
        <Button variant="default" onClick={onCancel}>{t('runbooks.cancel')}</Button>
      </Group>
    </Stack>
  )
}

/** Step-by-step fix guides for kinds of incident (issue #102). Leads write them, techs read them on the job. */
export default function Runbooks() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('incidents.assign')
  const [params, setParams] = useSearchParams()
  const query = useQuery({ queryKey: qk.runbooks, queryFn: () => get<{ runbooks: Runbook[]; kinds: RunbookKind[] }>('/api/runbooks') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.runbooks })
  useLiveEvent('runbooks.changed', refresh)
  const [editing, setEditing] = useState<'new' | string | null>(null)
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/runbooks/${id}`), onSuccess: () => { setParams({}); refresh() } })
  const move = useMutation({ mutationFn: (v: { id: string; step: number }) => post(`/api/runbooks/${v.id}/move`, { step: v.step }), onSuccess: refresh })
  const d = query.data
  const books = d?.runbooks ?? []
  const open = books.find((b) => b.id === params.get('open')) ?? books[0]
  const pick = (id: string) => { setEditing(null); setParams({ open: id }, { replace: true }) }
  const first = (k: RunbookKind) => books.find((b) => b.kinds.includes(k))?.id

  return (
    <Layout title={t('runbooks.title')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <PageHead title={t('runbooks.title')} desc={t('runbooks.intro')}
        actions={canEdit ? <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>{t('runbooks.add')}</Button> : undefined} />
      {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
      {(remove.error || move.error) && <Alert color="down" role="alert">{(remove.error || move.error)!.message}</Alert>}
      {query.isPending || !d ? <Loader aria-label={t('common.loading')} /> : (
        <Grid gap="md">
          <Grid.Col span={{ base: 12, md: 4 }}>
            <Paper withBorder radius="lg" p="xs">
              {books.length === 0 ? <Text size="sm" c="dimmed" p="xs">{t('runbooks.none')}</Text> : books.map((b) => (
                <NavLink key={b.id} variant="light" color="bit" style={{ borderRadius: 8 }} active={b.id === open?.id && editing !== 'new'} label={b.title} onClick={() => pick(b.id)}
                  description={b.kinds.length ? b.kinds.map((k) => t(`runbooks.kind.${k}`)).join(', ') : t('runbooks.noKind')} />
              ))}
            </Paper>
            {books.some((b) => b.starter) && <Text size="xs" c="dimmed" mt="xs">{t('runbooks.starterHint')}</Text>}
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 8 }}>
            <Paper withBorder radius="lg" p="md">
              {editing ? (
                <Editor key={editing} book={editing === 'new' ? null : open ?? null} kinds={d.kinds} onCancel={() => setEditing(null)}
                  onSaved={(id) => { refresh(); pick(id) }} />
              ) : open ? (
                <Stack gap="sm">
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <div>
                      <Title order={2} size="h3">{open.title}</Title>
                      <Group gap={6} mt={4}>
                        {open.kinds.map((k) => (
                          <Badge key={k} variant={first(k) === open.id ? 'light' : 'outline'} color={first(k) === open.id ? 'bit' : 'gray'} tt="none">
                            {t(`runbooks.kind.${k}`)}
                          </Badge>
                        ))}
                        {open.starter && <Badge variant="outline" color="warn" tt="none">{t('runbooks.starter')}</Badge>}
                      </Group>
                    </div>
                    {canEdit && (
                      <Group gap={4} wrap="nowrap">
                        <ActionIcon variant="default" aria-label={t('runbooks.up')} onClick={() => move.mutate({ id: open.id, step: -1 })}><IconArrowUp size={16} /></ActionIcon>
                        <ActionIcon variant="default" aria-label={t('runbooks.down')} onClick={() => move.mutate({ id: open.id, step: 1 })}><IconArrowDown size={16} /></ActionIcon>
                      </Group>
                    )}
                  </Group>
                  {open.kinds.some((k) => first(k) !== open.id) && <Text size="xs" c="dimmed">{t('runbooks.shadowed')}</Text>}
                  <Markdown source={open.body} />
                  {open.updated_at && (
                    <Text size="xs" c="dimmed">
                      {t('runbooks.changed', { who: open.by ?? '–', when: new Date(open.updated_at * 1000).toLocaleString(i18n.language) })}
                    </Text>
                  )}
                  {canEdit && (
                    <Group gap="xs">
                      <Button variant="default" onClick={() => setEditing(open.id)}>{t('runbooks.edit')}</Button>
                      <Button variant="subtle" color="down" loading={remove.isPending} onClick={() => remove.mutate(open.id)}>{t('runbooks.delete')}</Button>
                    </Group>
                  )}
                </Stack>
              ) : <Text c="dimmed">{t('runbooks.none')}</Text>}
            </Paper>
          </Grid.Col>
        </Grid>
      )}
    </Layout>
  )
}
