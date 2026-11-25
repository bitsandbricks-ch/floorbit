import { Alert, Anchor, Button, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useSearchParams } from 'react-router-dom'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { PublicPage } from '@/components/PublicPage'
import { type Figure, runSpeedtest } from './seatSpeed'

export interface SeatHelpState {
  seat: string
  problems: string[]
  outage: number | null
  status_url: string | null
  back_up: number | null
  report: 'open' | 'sent' | 'taken' | 'fixed' | 'ok' | null
  ahead: number
  /** What one speed test may move; null while speed tests are off. */
  speedtest: { test_mb: number } | null
}
type Done = 'thanks' | 'again' | 'ok'

const code = (e: unknown) => (e instanceof ApiError ? (e.data.code as string | undefined) ?? String(e.status) : e ? 'error' : null)
const REPORT_COLOR = { open: 'warn', sent: 'bit', taken: 'bit', fixed: 'up', ok: 'up' } as const

/** The seat's help page (``/help/<seat>?k=``, from the QR code on the seat): tap what is wrong
 *  and the crew comes over, see where the report stands, say it works again, and test the
 *  connection to the hall's server. No account, no name. */
export default function SeatHelp() {
  const { t } = useTranslation()
  const { seat: raw = '' } = useParams()
  const [params] = useSearchParams()
  const k = params.get('k') ?? ''
  const seat = raw.trim().toUpperCase()
  const api = `/api/helpdesk/seats/${encodeURIComponent(seat)}?k=${encodeURIComponent(k)}`
  const client = useQueryClient()
  const q = useQuery({ queryKey: qk.seatHelp(seat, k), queryFn: () => get<SeatHelpState>(api), retry: false, refetchInterval: 30_000 })
  const send = useMutation({
    mutationFn: (body: { problem: string } | { works: true }) => post<{ state: Done }>(api, body),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.seatHelp(seat, k) }),
  })
  const title = t('seatHelp.title', { seat })
  const failed = code(q.error) ?? code(send.error)
  const done = send.data?.state
  const s = q.data
  return (
    <PublicPage title={title}>
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="md">
          <Title order={1} size="h3">{title}</Title>
          {failed === 'invalid' && <Alert color="down" role="alert">{t('seatHelp.invalid')}</Alert>}
          {failed === 'busy' && <Alert color="warn" role="alert">{t('seatHelp.busy')}</Alert>}
          {failed && failed !== 'invalid' && failed !== 'busy' && <Alert color="down" role="alert">{t('publicPages.unreachable')}</Alert>}
          {done && <Alert color="up" role="status">{t(`seatHelp.done.${done}`, { seat })}</Alert>}
          {s && !done && (
            <>
              {s.outage && (
                <Alert color="down" role="status">
                  {t('seatHelp.outage', { count: s.outage })}
                  {s.status_url && <> <Anchor href={s.status_url}>{t('seatHelp.statusLink')}</Anchor></>}
                </Alert>
              )}
              {s.back_up && <Alert color="up" role="status">{t('seatHelp.backUp', { count: s.back_up })}</Alert>}
              {s.report && (
                <Alert color={REPORT_COLOR[s.report]} role="status">
                  {t(`seatHelp.report.${s.report}`)}
                  {s.report === 'open' && s.ahead > 0 && <> {t('seatHelp.ahead', { count: s.ahead })}</>}
                </Alert>
              )}
              <Text c="dimmed">{t('seatHelp.intro')}</Text>
              <Stack gap="xs">
                {s.problems.map((p) => (
                  <Button key={p} size="lg" variant="default" justify="flex-start" fullWidth loading={send.isPending && send.variables && 'problem' in send.variables && send.variables.problem === p}
                    disabled={send.isPending} onClick={() => send.mutate({ problem: p })}>
                    {t(`seatHelp.problem.${p}`, { defaultValue: p })}
                  </Button>
                ))}
              </Stack>
              {s.report && ['open', 'sent', 'taken'].includes(s.report) && (
                <Stack gap="xs" pt="sm" style={{ borderTop: '1px solid var(--bnb-line)' }}>
                  <Text c="dimmed" size="sm">{t('seatHelp.worksHint')}</Text>
                  <Button variant="light" color="up" fullWidth disabled={send.isPending} onClick={() => send.mutate({ works: true })}>{t('seatHelp.works')}</Button>
                </Stack>
              )}
            </>
          )}
          {s?.speedtest && done !== 'ok' && <SpeedTest seat={s.seat} k={k} testMb={s.speedtest.test_mb} />}
        </Stack>
      </Paper>
    </PublicPage>
  )
}

const UNITS: Record<Figure, string> = { down: 'Mbit/s', up: 'Mbit/s', ping: 'ms' }
const fmt = (n: number, lang: string) => new Intl.NumberFormat(lang, { maximumFractionDigits: n >= 100 ? 0 : 1, minimumFractionDigits: n >= 100 ? 0 : 1 }).format(n)

function SpeedTest({ seat, k, testMb }: { seat: string; k: string; testMb: number }) {
  const { t, i18n } = useTranslation()
  const [figures, setFigures] = useState<Partial<Record<Figure, number>> | null>(null)
  const [state, setState] = useState<'idle' | 'running' | 'saved' | 'failed'>('idle')
  const [error, setError] = useState('')
  const run = async () => {
    setFigures({})
    setState('running')
    try {
      await runSpeedtest(seat, k, (what, value) => setFigures((f) => ({ ...f, [what]: value })), testMb)
      setState('saved')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setState('failed')
    }
  }
  const number = (n: number | undefined) => (n == null ? '–' : fmt(n, i18n.language))
  return (
    <Stack gap="xs" pt="md" style={{ borderTop: '1px solid var(--bnb-line)' }} component="section" aria-labelledby="speed-title">
      <Title order={2} size="h4" id="speed-title">{t('seatHelp.speed.title')}</Title>
      <Text c="dimmed" size="sm">{t('seatHelp.speed.intro')}</Text>
      <Button onClick={() => { void run() }} loading={state === 'running'}>
        {state === 'idle' ? t('seatHelp.speed.run') : t('seatHelp.speed.again')}
      </Button>
      {figures && (
        <SimpleGrid cols={3} spacing="xs" component="dl" m={0}>
          {(['down', 'up', 'ping'] as const).map((f) => (
            <Paper key={f} bg="var(--bnb-raised)" radius="md" p="xs" ta="center">
              <Text component="dt" size="xs" c="dimmed">{t(`seatHelp.speed.${f}`)}</Text>
              <Text component="dd" m={0} fw={700} fz="lg" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {number(figures[f])} <Text span size="xs" fw={400} c="dimmed">{UNITS[f]}</Text>
              </Text>
            </Paper>
          ))}
        </SimpleGrid>
      )}
      {state === 'saved' && <Text c="up" size="sm" role="status">{t('seatHelp.speed.saved', { seat })}</Text>}
      {state === 'failed' && <Text c="down" size="sm" role="alert">{t('seatHelp.speed.failed', { error })}</Text>}
    </Stack>
  )
}
