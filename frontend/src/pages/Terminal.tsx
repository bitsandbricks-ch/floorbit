import { Alert, Badge, Box, Button, Group, Loader, Paper, PasswordInput, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { IconPlugConnected, IconX } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ApiError, del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { TerminalInfo, TerminalOutput } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { type TerminalHandle, TerminalView } from './terminal/TerminalView'

interface Open {
  id: string
  switch: string
}

/** A terminal on one switch with the tech's own login (issue #95). Every line typed is audited;
 *  the password lives only in this page's state until the connection is open. */
export default function TerminalPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const query = useQuery({ queryKey: qk.terminal, queryFn: () => get<TerminalInfo>('/api/terminal') })
  const [sw, setSw] = useState<string | null>(params.get('switch'))
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [open, setOpen] = useState<Open | null>(null)
  const start = useMutation({
    mutationFn: (body: Record<string, unknown>) => post<Open>('/api/terminal', body),
    onSuccess: (s) => {
      setOpen(s)
      void qc.invalidateQueries({ queryKey: qk.terminal })
    },
  })
  const info = query.data
  const ready = !!sw && (!info?.needs_login || (username.trim() !== '' && password !== ''))
  const submit = () => {
    if (!sw) return
    const body: Record<string, unknown> = { switch: sw, cols: 120, rows: 32 }
    if (info?.needs_login) Object.assign(body, { username: username.trim(), password })
    setPassword('')
    start.mutate(body)
  }
  const closed = () => void qc.invalidateQueries({ queryKey: qk.terminal })
  const others = info?.sessions.filter((s) => s.id !== open?.id) ?? []

  return (
    <Layout title={t('terminal.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('terminal.title')} desc={t('terminal.intro', { idle: info?.idle_minutes ?? 10, max: info?.max_minutes ?? 60 })} />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : info && !info.available ? (
          <Alert color="warn">{t('terminal.noPlugin')}</Alert>
        ) : info && !open && (
          <Paper withBorder radius="lg" p="md">
            <form autoComplete="off" onSubmit={(e) => { e.preventDefault(); submit() }}>
              <Stack gap="sm">
                <SimpleGrid cols={{ base: 1, sm: info.needs_login ? 3 : 1 }}>
                  <Select label={t('terminal.switch')} value={sw} onChange={setSw} searchable
                    data={[...new Set([...info.switches, ...(sw ? [sw] : [])])]} placeholder={t('terminal.pick')} />
                  {info.needs_login && (
                    <>
                      <TextInput label={t('terminal.username')} value={username} maxLength={64} autoComplete="off"
                        onChange={(e) => setUsername(e.currentTarget.value)} />
                      <PasswordInput label={t('terminal.password')} value={password} maxLength={256} autoComplete="off"
                        description={t('terminal.passwordHint')} onChange={(e) => setPassword(e.currentTarget.value)} />
                    </>
                  )}
                </SimpleGrid>
                {start.error && <Alert color="down" role="alert">{start.error.message}</Alert>}
                <Group justify="space-between" wrap="wrap">
                  <Text size="xs" c="dimmed">{t('terminal.audited')}</Text>
                  <Button type="submit" disabled={!ready} loading={start.isPending} leftSection={<IconPlugConnected size={16} />}>
                    {t('terminal.open')}
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>
        )}
        {open && <Session key={open.id} session={open} onLeave={() => { setOpen(null); closed() }} />}
        {!open && others.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Text fw={600} mb="xs">{t('terminal.yours')}</Text>
            <Stack gap={6}>
              {others.map((s) => (
                <Group key={s.id} justify="space-between">
                  <Text ff="monospace">{s.switch}</Text>
                  <Group gap="xs">
                    <Button size="xs" variant="default" onClick={() => setOpen({ id: s.id, switch: s.switch })}>{t('terminal.reattach')}</Button>
                    <Button size="xs" variant="subtle" color="down" onClick={() => void del(`/api/terminal/${s.id}`).finally(closed)}>
                      {t('terminal.close')}
                    </Button>
                  </Group>
                </Group>
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Layout>
  )
}

function Session({ session, onLeave }: { session: Open; onLeave: () => void }) {
  const { t } = useTranslation()
  const term = useRef<TerminalHandle | null>(null)
  const pending = useRef('')                       // output that came before the terminal was ready
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const [ended, setEnded] = useState<string | null>(null)
  const base = `/api/terminal/${encodeURIComponent(session.id)}`

  useEffect(() => {
    let stop = false
    let after = 0
    void (async () => {
      while (!stop) {
        try {
          const out = await get<TerminalOutput>(`${base}/output?after=${after}`)
          if (stop) return
          after = out.next
          if (out.data) {
            if (term.current) term.current.write(out.data)
            else pending.current += out.data
          }
          if (out.closed) {
            setEnded(out.closed)
            return
          }
          // The server waits for output; an empty answer at once means it couldn't: don't spin.
          if (!out.data) await new Promise((r) => setTimeout(r, 300))
        } catch (err) {
          if (stop) return
          setEnded(err instanceof ApiError && err.status === 404 ? t('terminal.gone') : (err as Error).message)
          return
        }
      }
    })()
    return () => {
      stop = true
    }
  }, [base, t])

  // Keystrokes go out one request after the other, so they reach the switch in order.
  const send = useCallback((data: string) => {
    queue.current = queue.current.then(() => post(`${base}/input`, { data }).catch(() => undefined))
  }, [base])
  const resize = useCallback((cols: number, rows: number) => {
    void post(`${base}/resize`, { cols, rows }).catch(() => undefined)
  }, [base])
  const ready = useCallback((h: TerminalHandle) => {
    term.current = h
    if (pending.current) h.write(pending.current)
    pending.current = ''
  }, [])
  const close = () => {
    if (!ended) void del(base).catch(() => undefined)
    onLeave()
  }

  return (
    <Paper withBorder radius="lg" p="sm">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <Text fw={700} ff="monospace">{session.switch}</Text>
          <Badge size="sm" variant="light" color={ended ? 'gray' : 'up'} tt="none" miw="max-content">
            {ended ? t('terminal.closed') : t('terminal.connected')}
          </Badge>
        </Group>
        <Button size="xs" variant="default" leftSection={<IconX size={14} />} onClick={close}>
          {ended ? t('terminal.back') : t('terminal.close')}
        </Button>
      </Group>
      {ended && <Alert color="gray" mb="xs">{ended}</Alert>}
      <Box h={{ base: 420, md: 560 }} style={{ background: '#0f1419', borderRadius: 8, padding: 6 }}>
        <TerminalView onReady={ready} onData={(d) => { if (!ended) send(d) }} onResize={resize} />
      </Box>
      <Text size="xs" c="dimmed" mt="xs">{t('terminal.audited')}</Text>
    </Paper>
  )
}
