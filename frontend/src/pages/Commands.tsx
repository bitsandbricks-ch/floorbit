import {
  ActionIcon, Alert, Badge, Button, Code, Group, Loader, Modal, MultiSelect, Paper, PasswordInput, ScrollArea,
  SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Textarea, Title, Tooltip,
} from '@mantine/core'
import { IconFileDiff, IconPlayerPlay, IconPlus, IconTerminal2, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ApiError, del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { CommandInfo, CommandRun, CommandTemplate } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

interface RunBody {
  template: string
  switches: string[]
  port?: string
  username?: string
  password?: string
  confirm?: boolean
}

/** Saved commands on one or many switches, output side by side (issue #94). Nobody types a command:
 *  the crew picks a template. The switch password lives only in this page's state, for one run. */
export default function Commands() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const query = useQuery({ queryKey: qk.commands, queryFn: () => get<CommandInfo>('/api/commands') })
  const [templateId, setTemplateId] = useState<string | null>(params.get('template'))
  const [switches, setSwitches] = useState<string[]>(() => params.getAll('switch'))
  const [port, setPort] = useState(params.get('port') ?? '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirming, setConfirming] = useState<RunBody | null>(null)
  const [editing, setEditing] = useState(false)
  const canTerminal = useCan('terminal.open')
  const canConfigs = useCan('configs.read')
  const run = useMutation({
    mutationFn: (body: RunBody) => post<CommandRun>('/api/commands/run', body),
    onError: (err, body) => {
      // The server asks once more before a change template runs.
      if (err instanceof ApiError && err.status === 409 && err.data.confirm) setConfirming(body)
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => del(`/api/commands/templates/${encodeURIComponent(id)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.commands }),
  })

  const info = query.data
  const tpl = info?.templates.find((x) => x.id === templateId) ?? info?.templates[0]
  const ready = !!tpl && switches.length > 0 && (!tpl.needs_port || port.trim() !== '')
    && (!info?.needs_login || (username.trim() !== '' && password !== ''))
  const submit = (confirm = false) => {
    if (!tpl) return
    const body: RunBody = { template: tpl.id, switches, ...(tpl.needs_port ? { port: port.trim() } : {}) }
    if (info?.needs_login) Object.assign(body, { username: username.trim(), password })
    setPassword('')
    setConfirming(null)
    if (tpl.kind === 'change' && !confirm) {
      setConfirming(body)
      return
    }
    run.mutate({ ...body, ...(confirm ? { confirm: true } : {}) })
  }
  const runError = run.error instanceof ApiError && run.error.data.confirm ? null : run.error
  const custom = info?.templates.filter((x) => !x.builtin) ?? []

  return (
    <Layout title={t('commands.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('commands.title')} desc={t('commands.intro')}
        actions={
          <>
            {canConfigs && (
              <Button variant="default" component="a" href="/configs" leftSection={<IconFileDiff size={16} />}>
                {t('commands.configs')}
              </Button>
            )}
            {canTerminal && (
              <Button variant="default" component="a" href="/terminal" leftSection={<IconTerminal2 size={16} />}>
                {t('commands.terminal')}
              </Button>
            )}
            {info?.may_edit && (
              <Button variant="default" leftSection={<IconPlus size={16} />} onClick={() => setEditing(true)}>
                {t('commands.newTemplate')}
              </Button>
            )}
          </>
        } />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : info && !info.available ? (
          <Alert color="warn">{t('commands.noPlugin')}</Alert>
        ) : info && (
          <Paper withBorder radius="lg" p="md">
            <form autoComplete="off" onSubmit={(e) => { e.preventDefault(); submit() }}>
              <Stack gap="sm">
                <SimpleGrid cols={{ base: 1, sm: tpl?.needs_port ? 3 : 2 }}>
                  <Select label={t('commands.template')} value={tpl?.id ?? null} allowDeselect={false}
                    onChange={setTemplateId}
                    data={(['show', 'change'] as const)
                      .map((kind) => ({
                        group: t(`commands.kind.${kind}`),
                        items: info.templates.filter((x) => x.kind === kind).map((x) => ({ value: x.id, label: x.label })),
                      }))
                      .filter((g) => g.items.length > 0)} />
                  <MultiSelect label={t('commands.switches')} value={switches} onChange={setSwitches} searchable
                    data={[...new Set([...info.switches, ...switches])]} maxValues={info.max_switches}
                    placeholder={switches.length ? undefined : t('commands.pickSwitches')} />
                  {tpl?.needs_port && (
                    <TextInput label={t('commands.port')} placeholder="Gi1/0/3" value={port} maxLength={48}
                      onChange={(e) => setPort(e.currentTarget.value)} />
                  )}
                </SimpleGrid>
                {tpl && (
                  <Group gap={6} wrap="wrap">
                    {tpl.kind === 'change' && <Badge color="warn" variant="light" tt="none">{t('commands.changes')}</Badge>}
                    {tpl.commands.map((c) => (
                      <Code key={c}>{tpl.needs_port && port.trim() ? c.replace('{port}', port.trim()) : c}</Code>
                    ))}
                  </Group>
                )}
                {info.needs_login && (
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    <TextInput label={t('commands.username')} value={username} maxLength={64}
                      autoComplete="off" onChange={(e) => setUsername(e.currentTarget.value)} />
                    <PasswordInput label={t('commands.password')} value={password} maxLength={256}
                      autoComplete="off" description={t('commands.passwordHint')}
                      onChange={(e) => setPassword(e.currentTarget.value)} />
                  </SimpleGrid>
                )}
                <Group justify="space-between" wrap="wrap">
                  <Text size="xs" c="dimmed">{t('commands.via', { plugin: info.plugin, platform: info.platform })}</Text>
                  <Button type="submit" disabled={!ready} loading={run.isPending} leftSection={<IconPlayerPlay size={16} />}
                    color={tpl?.kind === 'change' ? 'warn' : undefined}>
                    {t('commands.run', { count: switches.length })}
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>
        )}
        {runError && <Alert color="down" role="alert">{runError.message}</Alert>}
        {run.data && <Results run={run.data} terminal={canTerminal} />}
        {info?.may_edit && custom.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Title order={2} size="h4" mb="xs">{t('commands.yourTemplates')}</Title>
            <Stack gap={6}>
              {custom.map((x) => (
                <Group key={x.id} justify="space-between" wrap="nowrap">
                  <Group gap={6} wrap="wrap">
                    <Text fw={600} size="sm">{x.label}</Text>
                    <Badge size="sm" variant="light" color={x.kind === 'change' ? 'warn' : 'gray'} tt="none">
                      {t(`commands.kind.${x.kind}`)}
                    </Badge>
                    <Text size="xs" c="dimmed" ff="monospace">{x.commands.join(' ; ')}</Text>
                  </Group>
                  <Tooltip label={t('commands.delete')}>
                    <ActionIcon variant="subtle" color="down" aria-label={t('commands.deleteNamed', { name: x.label })}
                      loading={remove.isPending && remove.variables === x.id} onClick={() => remove.mutate(x.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
      <Modal opened={!!confirming} onClose={() => setConfirming(null)} title={t('commands.confirmTitle')}>
        <Stack gap="sm">
          <Text size="sm">{t('commands.confirmText', { count: confirming?.switches.length ?? 0, label: tpl?.label })}</Text>
          <Group gap={6}>{tpl?.commands.map((c) => <Code key={c}>{c.replace('{port}', confirming?.port ?? '')}</Code>)}</Group>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(null)}>{t('commands.cancel')}</Button>
            <Button color="warn" onClick={() => {
              const body = confirming
              setConfirming(null)
              if (body) run.mutate({ ...body, confirm: true })
            }}>{t('commands.confirmRun')}</Button>
          </Group>
        </Stack>
      </Modal>
      {editing && <TemplateDialog onClose={() => setEditing(false)} />}
    </Layout>
  )
}

function Results({ run, terminal }: { run: CommandRun; terminal: boolean }) {
  const { t } = useTranslation()
  const failed = run.results.filter((r) => !r.ok).length
  return (
    <Stack gap="sm">
      <Group gap="xs">
        <Title order={2} size="h4">{run.label}{run.port ? ` · ${run.port}` : ''}</Title>
        <Badge variant="light" color={failed ? 'warn' : 'up'} tt="none">
          {failed ? t('commands.someFailed', { count: failed, total: run.results.length }) : t('commands.allOk', { count: run.results.length })}
        </Badge>
      </Group>
      <SimpleGrid cols={{ base: 1, md: Math.min(run.results.length, 2), xl: Math.min(run.results.length, 3) }}>
        {run.results.map((r) => (
          <Paper key={r.switch} withBorder radius="lg" p="sm" miw={0}>
            <Group justify="space-between" mb={6} wrap="nowrap">
              <Text fw={700} ff="monospace">{r.switch}</Text>
              <Group gap={6} wrap="nowrap">
                {terminal && (
                  <Tooltip label={t('commands.openTerminal', { name: r.switch })}>
                    <ActionIcon variant="subtle" component="a" href={`/terminal?switch=${encodeURIComponent(r.switch)}`}
                      aria-label={t('commands.openTerminal', { name: r.switch })}>
                      <IconTerminal2 size={16} />
                    </ActionIcon>
                  </Tooltip>
                )}
                {r.ms !== undefined && <Text size="xs" c="dimmed">{t('commands.took', { s: (r.ms / 1000).toFixed(1) })}</Text>}
                <Badge size="sm" variant="light" color={r.ok ? 'up' : 'down'} tt="none" miw="max-content">
                  {r.ok ? t('commands.ok') : t('commands.failed')}
                </Badge>
              </Group>
            </Group>
            {r.error && <Text size="sm" c="down" mb={6}>{r.error}</Text>}
            {r.output && (
              <ScrollArea.Autosize mah={480} type="auto">
                <Code block fz="xs" style={{ whiteSpace: 'pre' }}>{r.output}</Code>
              </ScrollArea.Autosize>
            )}
          </Paper>
        ))}
      </SimpleGrid>
    </Stack>
  )
}

function TemplateDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [id, setId] = useState('')
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState<CommandTemplate['kind']>('show')
  const [text, setText] = useState('')
  const save = useMutation({
    mutationFn: () => put(`/api/commands/templates/${encodeURIComponent(id.trim())}`, { label, kind, commands: text }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.commands })
      onClose()
    },
  })
  return (
    <Modal opened onClose={onClose} title={t('commands.newTemplate')}>
      <form onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <Stack gap="sm">
          {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
          <TextInput label={t('commands.label')} value={label} maxLength={80} required onChange={(e) => setLabel(e.currentTarget.value)} />
          <TextInput label={t('commands.id')} description={t('commands.idHint')} value={id} maxLength={32} required
            onChange={(e) => setId(e.currentTarget.value.toLowerCase())} />
          <SegmentedControl value={kind} onChange={(v) => setKind(v as CommandTemplate['kind'])}
            data={[{ value: 'show', label: t('commands.kind.show') }, { value: 'change', label: t('commands.kind.change') }]} />
          <Text size="xs" c="dimmed">{t(`commands.kindHint.${kind}`)}</Text>
          <Textarea label={t('commands.commands')} description={t('commands.commandsHint')} value={text} required autosize
            minRows={3} styles={{ input: { fontFamily: 'var(--mantine-font-family-monospace)' } }}
            onChange={(e) => setText(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('commands.cancel')}</Button>
            <Button type="submit" loading={save.isPending}>{t('commands.save')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
