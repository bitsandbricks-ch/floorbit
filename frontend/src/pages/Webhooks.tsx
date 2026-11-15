import {
  Alert, Badge, Button, Checkbox, Code, CopyButton, Group, Loader, Paper, SimpleGrid, Stack, Switch, Text, TextInput, Title,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Webhook } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

type Answer = { webhooks: Webhook[]; events: string[] }
type WithSecret = { webhook: Webhook; secret: string }
type Ping = { ok: boolean; status: number | null; error: string | null }

function EventPicker({ events, value, onChange }: { events: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const { t } = useTranslation()
  return (
    <Checkbox.Group label={t('webhooks.events')} value={value} onChange={onChange}>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing={6} mt={6}>
        {events.map((e) => (
          <Checkbox key={e} value={e} label={t(`webhooks.event.${e}`, { defaultValue: e })} description={<Code>{e}</Code>} />
        ))}
      </SimpleGrid>
    </Checkbox.Group>
  )
}

function NewHook({ events, onMade }: { events: string[]; onMade: (m: WithSecret) => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [picked, setPicked] = useState<string[]>(['switch.down', 'switch.up', 'incident.opened'])
  const add = useMutation({
    mutationFn: () => post<WithSecret>('/api/settings/webhooks', { name: name.trim(), url: url.trim(), events: picked }),
    onSuccess: (m) => { setName(''); setUrl(''); onMade(m) },
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{t('webhooks.new')}</Title>
      <Stack gap="sm">
        <Group grow align="flex-start">
          <TextInput label={t('webhooks.name')} value={name} maxLength={60} onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput label={t('webhooks.url')} placeholder="https://hooks.example.com/floorbit" value={url} maxLength={500}
            onChange={(e) => setUrl(e.currentTarget.value)} />
        </Group>
        <EventPicker events={events} value={picked} onChange={setPicked} />
        {add.error && <Alert color="down" role="alert">{add.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={add.isPending} disabled={!name.trim() || !url.trim() || picked.length === 0}
            onClick={() => add.mutate()}>{t('webhooks.add')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

function Hook({ hook, events, onSecret, onChanged }: {
  hook: Webhook; events: string[]; onSecret: (m: WithSecret) => void; onChanged: () => void
}) {
  const { t, i18n } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [picked, setPicked] = useState(hook.events)
  const [ping, setPing] = useState<Ping | null>(null)
  const change = useMutation({
    mutationFn: (body: Partial<Webhook>) => patch(`/api/settings/webhooks/${hook.id}`, body),
    onSuccess: () => { setEditing(false); onChanged() },
  })
  const test = useMutation({ mutationFn: () => post<Ping>(`/api/settings/webhooks/${hook.id}/test`), onSuccess: (p) => { setPing(p); onChanged() } })
  const rotate = useMutation({ mutationFn: () => post<WithSecret>(`/api/settings/webhooks/${hook.id}/secret`), onSuccess: onSecret })
  const remove = useMutation({ mutationFn: () => del(`/api/settings/webhooks/${hook.id}`), onSuccess: onChanged })
  const time = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { dateStyle: 'short', timeStyle: 'medium' })
  const error = change.error ?? test.error ?? rotate.error ?? remove.error
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={0} style={{ minWidth: 0 }}>
            <Group gap={6}>
              <Text fw={600}>{hook.name}</Text>
              {hook.last && (hook.last.ok
                ? <Badge variant="light" color="up" tt="none">{t('webhooks.lastOk')}</Badge>
                : <Badge variant="light" color="down" tt="none">{t('webhooks.lastFailed')}</Badge>)}
            </Group>
            <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{hook.url}</Text>
          </Stack>
          <Switch aria-label={t('webhooks.active', { name: hook.name })} checked={hook.active} disabled={change.isPending}
            onChange={(e) => change.mutate({ active: e.currentTarget.checked })} />
        </Group>
        {editing ? (
          <>
            <EventPicker events={events} value={picked} onChange={setPicked} />
            <Group justify="flex-end" gap="xs">
              <Button size="compact-sm" variant="default" onClick={() => { setPicked(hook.events); setEditing(false) }}>{t('webhooks.cancel')}</Button>
              <Button size="compact-sm" disabled={picked.length === 0} loading={change.isPending}
                onClick={() => change.mutate({ events: picked })}>{t('webhooks.save')}</Button>
            </Group>
          </>
        ) : (
          <Group gap={4}>
            {hook.events.map((e) => <Badge key={e} variant="outline" color="gray" tt="none">{t(`webhooks.event.${e}`, { defaultValue: e })}</Badge>)}
          </Group>
        )}
        {ping && (
          <Alert color={ping.ok ? 'up' : 'down'} role="status" withCloseButton onClose={() => setPing(null)}>
            {ping.ok ? t('webhooks.pingOk', { status: ping.status }) : t('webhooks.pingFailed', { error: ping.error })}
          </Alert>
        )}
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        {hook.deliveries.length > 0 && (
          <Stack gap={2}>
            <Text size="xs" fw={600}>{t('webhooks.recent')}</Text>
            {hook.deliveries.slice(0, 5).map((d) => (
              <Text key={`${d.delivery}-${d.attempt}`} size="xs" c={d.ok ? 'dimmed' : 'down'}>
                {time(d.at)} · <Code>{d.event}</Code> · {d.ok ? d.status : d.error}
                {d.attempt > 1 ? ` · ${t('webhooks.attempt', { n: d.attempt })}` : ''}
              </Text>
            ))}
          </Stack>
        )}
        <Group gap="xs">
          <Button size="compact-sm" variant="default" loading={test.isPending} onClick={() => test.mutate()}>{t('webhooks.test')}</Button>
          {!editing && <Button size="compact-sm" variant="default" onClick={() => setEditing(true)}>{t('webhooks.edit')}</Button>}
          <ConfirmButton size="compact-sm" variant="default" danger label={t('webhooks.rotate')} question={t('webhooks.rotateQuestion')}
            onConfirm={() => rotate.mutate()} />
          <ConfirmButton size="compact-sm" variant="default" danger label={t('webhooks.remove')}
            question={t('webhooks.removeQuestion', { name: hook.name })} onConfirm={() => remove.mutate()} />
        </Group>
      </Stack>
    </Paper>
  )
}

/** Send chosen events to other tools as signed JSON POSTs. */
export default function Webhooks() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.webhooks, queryFn: () => get<Answer>('/api/settings/webhooks') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.webhooks })
  const [secret, setSecret] = useState<WithSecret | null>(null)
  const shown = (m: WithSecret) => { setSecret(m); refresh() }
  const d = query.data

  return (
    <Layout title={t('webhooks.title')} back={{ href: '/settings', label: t('webhooks.settings') }}>
      <PageHead title={t('webhooks.title')} desc={t('webhooks.intro')} />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {secret && (
          <Alert color="up" role="status" withCloseButton onClose={() => setSecret(null)} title={t('webhooks.secretTitle', { name: secret.webhook.name })}>
            <Stack gap="xs">
              <Text size="sm">{t('webhooks.secretHelp')}</Text>
              <Group gap="xs" wrap="nowrap">
                <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{secret.secret}</Code>
                <CopyButton value={secret.secret}>
                  {({ copied, copy }) => (
                    <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('webhooks.copied') : t('webhooks.copy')}</Button>
                  )}
                </CopyButton>
              </Group>
            </Stack>
          </Alert>
        )}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            {d.webhooks.length === 0 && <Text size="sm" c="dimmed">{t('webhooks.none')}</Text>}
            {d.webhooks.map((h) => <Hook key={h.id} hook={h} events={d.events} onSecret={shown} onChanged={refresh} />)}
            <NewHook events={d.events} onMade={shown} />
            <Text size="sm" c="dimmed">{t('webhooks.docs')}</Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
