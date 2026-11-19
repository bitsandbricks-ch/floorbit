import {
  Alert, Button, Group, Modal, NumberInput, PasswordInput, ScrollArea, Select, SimpleGrid, Stack, Switch, Text, TextInput,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { GameServer, RconAnswer } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { EntitySelect } from '@/components/EntitySelect'

/** A game server's settings and its RCON console (issue #472), opened from the Services page. */

interface Form { name: string; game: string; host: string; port: number | string; query: string; rcon_port: number | string; rcon_password: string; clear_rcon: boolean; runs_on: string }

export function ServerModal({ server, onClose }: { server: GameServer | null; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState<Form>({
    name: server?.name ?? '', game: server?.game ?? '', host: server?.host ?? '', port: server?.port ?? 27015,
    query: server?.query ?? 'a2s', rcon_port: server?.rcon_port ?? '', rcon_password: '', clear_rcon: false,
    runs_on: server?.runs_on ?? '',
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
        <EntitySelect kind="devices" label={t('gameServers.runsOn')} description={t('gameServers.runsOnHint')}
          value={form.runs_on} onChange={(v) => set({ runs_on: v })} />
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

export function RconConsole({ server, onClose }: { server: GameServer; onClose: () => void }) {
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
