import { ActionIcon, Alert, Button, Group, Paper, PasswordInput, Select, SimpleGrid, Stack, Text, TextInput, Title, Tooltip, VisuallyHidden } from '@mantine/core'
import { IconPlugConnected, IconPlus, IconTerminal2, IconX } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ApiError, del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { TerminalInfo, TerminalOutput } from '@/api/types'
import { Layout } from '@/components/Layout'
import { type TerminalHandle, TerminalView } from './terminal/TerminalView'
import { LoadingState, ErrorBanner } from '@/components/ui'

interface Open {
  id: string
  switch: string
}

/** The tab with the connect form. */
const NEW = 'new'
/** floorbit/terminal.py MAX_PER_ACCOUNT: the server refuses a fourth. */
const MAX_OPEN = 3

/** A workspace of switch terminals, one tab per device (issues #95, #1207). Every line typed is
 *  audited; the password lives only in this page's state until the connection is open. Each tab
 *  stays mounted while another shows, so its scrollback and its output stream keep going. */
export default function TerminalPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const query = useQuery({ queryKey: qk.terminal, queryFn: () => get<TerminalInfo>('/api/terminal') })
  const info = query.data
  const [tabs, setTabs] = useState<Open[]>([])
  const [ended, setEnded] = useState<Record<string, string>>({})
  const [active, setActive] = useState<string>(NEW)
  const [adopted, setAdopted] = useState(false)

  // Terminals still open from before (a reload, another browser tab) come back as tabs, unless the
  // address asks for a new one on a switch. Set while rendering, once, when the list first arrives.
  if (info && !adopted) {
    setAdopted(true)
    if (info.sessions.length) {
      setTabs(info.sessions.map((s) => ({ id: s.id, switch: s.switch })))
      if (!params.get('switch')) setActive(info.sessions[0].id)
    }
  }

  const opened = (s: Open) => {
    setTabs((list) => [...list.filter((x) => x.id !== s.id), s])
    setActive(s.id)
    void qc.invalidateQueries({ queryKey: qk.terminal })
  }
  const close = (id: string) => {
    if (!ended[id]) void del(`/api/terminal/${encodeURIComponent(id)}`).catch(() => undefined)
    const at = tabs.findIndex((x) => x.id === id)
    const rest = tabs.filter((x) => x.id !== id)
    setTabs(rest)
    if (active === id) setActive(rest[Math.min(at, rest.length - 1)]?.id ?? NEW)
    void qc.invalidateQueries({ queryKey: qk.terminal })
  }
  const onEnded = useCallback((id: string, why: string) => setEnded((e) => ({ ...e, [id]: why })), [])
  const live = tabs.filter((x) => !ended[x.id]).length
  const full = live >= MAX_OPEN

  return (
    <Layout title={t('terminal.title')} back={{ href: '/', label: t('common.floorPlan') }} full>
      <div className="fb-term">
        <div className="fb-term-tabs" role="tablist" aria-label={t('terminal.tabs')}>
          {tabs.map((s) => (
            <div key={s.id} className="fb-term-tab" data-active={active === s.id || undefined}>
              <button type="button" role="tab" aria-selected={active === s.id} aria-controls={`term-${s.id}`}
                onClick={() => setActive(s.id)} className="fb-term-tab-name">
                <span className={`fb-dot ${ended[s.id] ? '' : 'up'}`} aria-hidden="true" />
                <span>{s.switch}</span>
                <VisuallyHidden>{ended[s.id] ? t('terminal.closed') : t('terminal.connected')}</VisuallyHidden>
              </button>
              <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => close(s.id)}
                aria-label={t('terminal.closeTab', { name: s.switch })}>
                <IconX size={14} />
              </ActionIcon>
            </div>
          ))}
          <Tooltip label={t('terminal.full', { count: MAX_OPEN })} disabled={!full}>
            <button type="button" role="tab" aria-selected={active === NEW} aria-controls="term-new"
              className="fb-term-tab fb-term-tab-new" data-active={active === NEW || undefined} onClick={() => setActive(NEW)}>
              <IconPlus size={14} aria-hidden="true" />
              <span>{t('terminal.new')}</span>
            </button>
          </Tooltip>
        </div>
        <div className="fb-term-body">
          {tabs.map((s) => (
            <div key={s.id} id={`term-${s.id}`} role="tabpanel" className="fb-term-pane" hidden={active !== s.id}>
              <Session session={s} visible={active === s.id} ended={ended[s.id] ?? null} onEnded={onEnded}
                onClose={() => close(s.id)} />
            </div>
          ))}
          {active === NEW && (
            <div id="term-new" role="tabpanel" className="fb-term-new">
              <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
              {query.isPending ? <LoadingState /> : info && !info.available ? (
                <Alert color="warn">{t('terminal.noPlugin')}</Alert>
              ) : info && (
                <Connect info={info} full={full} initial={params.get('switch')} onOpened={opened} />
              )}
            </div>
          )}
        </div>
        <Text size="xs" c="dimmed" className="fb-term-foot">
          {t('terminal.audited')} {info && t('terminal.limits', { idle: info.idle_minutes, max: info.max_minutes })}
        </Text>
      </div>
    </Layout>
  )
}

function Connect({ info, full, initial, onOpened }: { info: TerminalInfo; full: boolean; initial: string | null; onOpened: (s: Open) => void }) {
  const { t } = useTranslation()
  const [sw, setSw] = useState<string | null>(initial)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const start = useMutation({
    mutationFn: (body: Record<string, unknown>) => post<Open>('/api/terminal', body),
    onSuccess: (s) => { setSw(null); onOpened(s) },
  })
  const ready = !!sw && !full && (!info.needs_login || (username.trim() !== '' && password !== ''))
  const submit = () => {
    if (!sw) return
    const body: Record<string, unknown> = { switch: sw, cols: 120, rows: 32 }
    if (info.needs_login) Object.assign(body, { username: username.trim(), password })
    setPassword('')
    start.mutate(body)
  }
  return (
    <Paper withBorder radius="md" p="lg" className="fb-term-connect">
      <form autoComplete="off" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <Stack gap="sm">
          <Group gap="xs" wrap="nowrap">
            <IconTerminal2 size={20} aria-hidden="true" />
            <Title order={2} size="h4">{t('terminal.newTitle')}</Title>
          </Group>
          <Text size="sm" c="dimmed">{t('terminal.intro')}</Text>
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
          {full && <Alert color="warn">{t('terminal.full', { count: MAX_OPEN })}</Alert>}
          {start.error && <Alert color="down" role="alert">{start.error.message}</Alert>}
          <Group justify="flex-end">
            <Button type="submit" disabled={!ready} loading={start.isPending} leftSection={<IconPlugConnected size={16} />}>
              {t('terminal.open')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}

function Session({ session, visible, ended, onEnded, onClose }: {
  session: Open; visible: boolean; ended: string | null; onEnded: (id: string, why: string) => void; onClose: () => void
}) {
  const { t } = useTranslation()
  const term = useRef<TerminalHandle | null>(null)
  const pending = useRef('')                       // output that came before the terminal was ready
  const queue = useRef<Promise<unknown>>(Promise.resolve())
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
            onEnded(session.id, out.closed)
            return
          }
          // The server waits for output; an empty answer at once means it couldn't: don't spin.
          if (!out.data) await new Promise((r) => setTimeout(r, 300))
        } catch (err) {
          if (stop) return
          onEnded(session.id, err instanceof ApiError && err.status === 404 ? t('terminal.gone') : (err as Error).message)
          return
        }
      }
    })()
    return () => {
      stop = true
    }
  }, [base, t, onEnded, session.id])

  // Back on this tab: the keys go to it.
  useEffect(() => {
    if (visible) term.current?.focus()
  }, [visible])

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

  return (
    <>
      {ended && (
        <Alert color="gray" radius={0} className="fb-term-ended">
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text size="sm">{t('terminal.endedOn', { name: session.switch })} {ended}</Text>
            <Button size="xs" variant="default" leftSection={<IconX size={14} />} onClick={onClose}>{t('terminal.closeTabShort')}</Button>
          </Group>
        </Alert>
      )}
      <div className="fb-term-screen">
        <TerminalView onReady={ready} onData={(d) => { if (!ended) send(d) }} onResize={resize} />
      </div>
    </>
  )
}
