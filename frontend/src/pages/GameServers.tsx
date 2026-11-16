import {
  Alert, Badge, Button, Group, Modal, NumberInput, Paper, PasswordInput, ScrollArea, Select, SimpleGrid, Stack, Switch,
  Text, TextInput, Title,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { GameServer, GameServerList, RconAnswer } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { Sparkline } from '@/widgets/Sparkline'

const TONE = { up: 'up', down: 'down', unknown: 'gray' } as const

/** Game servers (issue #472): up or down, players, map and ping, and an RCON console. */
export default function GameServers() {
  const { t } = useTranslation()
  const canSetUp = useCan('settings.manage')
  const canRcon = useCan('games.rcon')
  const list = useQuery({
    queryKey: qk.gameServers, queryFn: () => get<GameServerList>('/api/game-servers'), refetchInterval: 15_000,
  })
  const [editing, setEditing] = useState<GameServer | 'new' | null>(null)
  const [console_, setConsole] = useState<GameServer | null>(null)
  const data = list.data
  const servers = data?.servers ?? []
  return (
    <Layout title={t('gameServers.title')}>
      <PageHead title={t('gameServers.title')} desc={t('gameServers.intro')}
        actions={canSetUp && <Button onClick={() => setEditing('new')}>{t('gameServers.add')}</Button>} />
      <Stack gap="md">
        {data && servers.length > 0 && (
          <Text c="dimmed">
            {t('gameServers.summary', { up: data.counts.up, count: servers.length, players: data.players })}
            {data.via_agent ? ` · ${t('gameServers.viaAgent')}` : ''}
          </Text>
        )}
        {list.error && <Alert color="down" role="alert">{list.error.message}</Alert>}
        {data && servers.length === 0 && (
          <Paper withBorder radius="lg" p="md"><Text c="dimmed">{t(canSetUp ? 'gameServers.emptyAdmin' : 'gameServers.empty')}</Text></Paper>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {servers.map((s) => (
            <ServerCard key={s.id} server={s} canSetUp={canSetUp} canRcon={canRcon}
              onEdit={() => setEditing(s)} onConsole={() => setConsole(s)} />
          ))}
        </SimpleGrid>
      </Stack>
      {editing && <ServerModal server={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {console_ && <RconConsole server={console_} onClose={() => setConsole(null)} />}
    </Layout>
  )
}

function ServerCard({ server: s, canSetUp, canRcon, onEdit, onConsole }: {
  server: GameServer; canSetUp: boolean; canRcon: boolean; onEdit: () => void; onConsole: () => void
}) {
  const { t } = useTranslation()
  const info = s.info
  const points = s.history.map(([, n]) => n ?? 0)
  return (
    <Paper withBorder radius="lg" p="md" aria-label={s.name} component="section">
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Title order={3} size="h4" style={{ overflowWrap: 'anywhere' }}>{s.name}</Title>
          <Badge color={TONE[s.status]} variant="light">{t(`gameServers.status.${s.status}`)}</Badge>
        </Group>
        <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
          {[s.game || info?.game, `${s.host}:${s.port}`].filter(Boolean).join(' · ')}
        </Text>
        {s.status === 'up' && info ? (
          <>
            {s.query !== 'tcp' && (
              <Group gap="xs" align="baseline">
                <Text fw={700} fz={28} lh={1}>{info.players}/{info.max_players}</Text>
                <Text size="sm" c="dimmed">{t('gameServers.players')}{info.bots ? ` · ${t('gameServers.bots', { count: info.bots })}` : ''}</Text>
              </Group>
            )}
            <Text size="sm">
              {[info.map && t('gameServers.map', { map: info.map }), info.ping_ms != null && `${info.ping_ms} ms`,
                info.version].filter(Boolean).join(' · ')}
            </Text>
            {s.query !== 'tcp' && points.length > 1 && <div style={{ height: 30 }}><Sparkline points={points} min={0} /></div>}
          </>
        ) : (
          <Text size="sm" c={s.status === 'down' ? 'down' : 'dimmed'}>{s.error || t('gameServers.notAsked')}</Text>
        )}
        {(canRcon || canSetUp) && (
          <Group gap={6} mt={4}>
            {canRcon && (
              <Button size="compact-sm" variant="default" disabled={!s.rcon} onClick={onConsole}
                title={s.rcon ? undefined : t('gameServers.noRcon')}>{t('gameServers.console')}</Button>
            )}
            {canSetUp && <Button size="compact-sm" variant="subtle" onClick={onEdit}>{t('gameServers.edit')}</Button>}
          </Group>
        )}
      </Stack>
    </Paper>
  )
}

interface Form { name: string; game: string; host: string; port: number | string; query: string; rcon_port: number | string; rcon_password: string; clear_rcon: boolean }

function ServerModal({ server, onClose }: { server: GameServer | null; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState<Form>({
    name: server?.name ?? '', game: server?.game ?? '', host: server?.host ?? '', port: server?.port ?? 27015,
    query: server?.query ?? 'a2s', rcon_port: server?.rcon_port ?? '', rcon_password: '', clear_rcon: false,
  })
  const done = () => { void qc.invalidateQueries({ queryKey: qk.gameServers }); onClose() }
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, rcon_port: form.rcon_port === '' ? null : form.rcon_port }
      return server ? put(`/api/game-servers/${server.id}`, body) : post('/api/game-servers', body)
    },
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: () => del(`/api/game-servers/${server!.id}`), onSuccess: done })
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch })
  return (
    <Modal opened onClose={onClose} title={server ? server.name : t('gameServers.add')} size="lg">
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <TextInput label={t('gameServers.name')} value={form.name} onChange={(e) => set({ name: e.currentTarget.value })} />
          <TextInput label={t('gameServers.game')} placeholder="Counter-Strike 2" value={form.game}
            onChange={(e) => set({ game: e.currentTarget.value })} />
          <TextInput label={t('gameServers.host')} placeholder="192.0.2.50" value={form.host}
            onChange={(e) => set({ host: e.currentTarget.value })} />
          <NumberInput label={t('gameServers.port')} min={1} max={65535} value={form.port} onChange={(v) => set({ port: v })} />
          <Select label={t('gameServers.query')} value={form.query} allowDeselect={false}
            data={['a2s', 'minecraft', 'tcp'].map((q) => ({ value: q, label: t(`gameServers.queries.${q}`) }))}
            onChange={(v) => set({ query: v ?? 'a2s' })} />
          <NumberInput label={t('gameServers.rconPort')} min={1} max={65535} value={form.rcon_port}
            onChange={(v) => set({ rcon_port: v })} />
        </SimpleGrid>
        <PasswordInput label={t('gameServers.rconPassword')} autoComplete="new-password" value={form.rcon_password}
          description={server?.rcon ? t('gameServers.rconKept') : t('gameServers.rconHint')}
          disabled={form.clear_rcon} onChange={(e) => set({ rcon_password: e.currentTarget.value })} />
        {server?.rcon && (
          <Switch label={t('gameServers.clearRcon')} checked={form.clear_rcon}
            onChange={(e) => set({ clear_rcon: e.currentTarget.checked })} />
        )}
        {(save.error || remove.error) && <Alert color="down" role="alert">{(save.error || remove.error)!.message}</Alert>}
        <Group justify="space-between">
          {server ? (
            <ConfirmButton variant="subtle" danger label={t('gameServers.remove')}
              question={t('gameServers.removeQuestion', { name: server.name })} onConfirm={() => remove.mutate()} />
          ) : <span />}
          <Button loading={save.isPending} disabled={!form.name.trim() || !form.host.trim() || !form.port}
            onClick={() => save.mutate()}>{t('gameServers.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

interface Line { command: string; answer?: string; error?: string }

function RconConsole({ server, onClose }: { server: GameServer; onClose: () => void }) {
  const { t } = useTranslation()
  const phone = useMediaQuery('(max-width: 48em)')
  const [command, setCommand] = useState('')
  const [lines, setLines] = useState<Line[]>([])
  const [confirming, setConfirming] = useState<string | null>(null)
  const send = useMutation({
    mutationFn: ({ cmd, confirm }: { cmd: string; confirm: boolean }) =>
      post<RconAnswer>(`/api/game-servers/rcon/${server.id}`, { command: cmd, confirm }),
    onSuccess: (r) => { setLines((l) => [...l, { command: r.command, answer: r.answer }]); setCommand(''); setConfirming(null) },
    onError: (err, { cmd }) => {
      // The server asks before commands that stop it, change the map or throw players out.
      if (err instanceof ApiError && err.data.confirm) { setConfirming(cmd); return }
      setLines((l) => [...l, { command: cmd, error: err.message }])
    },
  })
  const submit = () => { if (command.trim()) send.mutate({ cmd: command.trim(), confirm: false }) }
  return (
    <Modal opened onClose={onClose} title={t('gameServers.consoleTitle', { name: server.name })} size="xl" fullScreen={phone}>
      <Stack gap="sm">
        <ScrollArea h={phone ? 'calc(100dvh - 320px)' : 360} type="auto" className="fb-rcon"
          style={{ background: 'var(--mantine-color-dark-8)', borderRadius: 8 }}>
          <Stack gap={8} p="sm" ff="monospace" fz="sm" c="gray.2" role="log" aria-label={t('gameServers.answers')}>
            {lines.length === 0 && <Text c="gray.5" fz="sm">{t('gameServers.consoleEmpty')}</Text>}
            {lines.map((l, i) => (
              <div key={i}>
                <div style={{ color: 'var(--mantine-color-gray-5)' }}>&gt; {l.command}</div>
                {l.error
                  ? <div style={{ color: 'var(--mantine-color-red-4)' }}>{l.error}</div>
                  : <pre style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{l.answer || t('gameServers.noAnswer')}</pre>}
              </div>
            ))}
          </Stack>
        </ScrollArea>
        {confirming && (
          <Alert color="warn" title={t('gameServers.confirmTitle')}>
            <Text size="sm" mb="xs">{t('gameServers.confirmText', { command: confirming })}</Text>
            <Group gap="xs">
              <Button size="compact-sm" color="down" loading={send.isPending}
                onClick={() => send.mutate({ cmd: confirming, confirm: true })}>{t('gameServers.sendAnyway')}</Button>
              <Button size="compact-sm" variant="default" onClick={() => setConfirming(null)}>{t('common.cancel')}</Button>
            </Group>
          </Alert>
        )}
        <form onSubmit={(e) => { e.preventDefault(); submit() }}>
          <Group gap="xs" wrap="nowrap">
            <TextInput style={{ flex: 1 }} ff="monospace" aria-label={t('gameServers.command')} placeholder="status"
              autoComplete="off" autoFocus value={command} onChange={(e) => setCommand(e.currentTarget.value)} />
            <Button type="submit" loading={send.isPending && !confirming} disabled={!command.trim()}>{t('gameServers.send')}</Button>
          </Group>
        </form>
        <Text size="xs" c="dimmed">{t('gameServers.audited')}</Text>
      </Stack>
    </Modal>
  )
}
