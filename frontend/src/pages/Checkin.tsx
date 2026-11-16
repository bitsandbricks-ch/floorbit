import { Alert, Anchor, Button, Loader, Paper, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { IconCalendarTime, IconCircleCheck, IconPlugConnectedX } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { CheckinInfo } from '@/api/types'
import { PublicPage } from '@/components/PublicPage'

type Wired = 'pending' | 'verified' | 'not_wired' | 'unverified'
type Done = { seat: string; username: string; wired?: Wired | null }
type Form = { pin: string; seat: string; username: string }

type NavigatorUAData = { mobile?: boolean }

/** What this device looks like: a phone or tablet is never the PC at the seat. A hint only: the
 *  switches decide in the background whether a wired PC on one seat port sent it. */
function deviceClass(): 'pc' | 'mobile' | 'unknown' {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return 'unknown'
  const hints = (navigator as Navigator & { userAgentData?: NavigatorUAData }).userAgentData
  const touchOnly = window.matchMedia?.('(pointer: coarse)').matches && !window.matchMedia?.('(any-pointer: fine)').matches
  const small = Math.min(window.screen?.width ?? 0, window.screen?.height ?? 0) < 600
  if (hints?.mobile || /Mobile|Android|iPhone|iPad/i.test(navigator.userAgent) || (touchOnly && small)) return 'mobile'
  return hints?.mobile === false || window.matchMedia?.('(pointer: fine)').matches ? 'pc' : 'unknown'
}

/** The PIN as printed: upper case, no spaces or dashes ("k7m-2x" is "K7M2X"). */
function cleanPin(pin: string) {
  return pin.replace(/[\s-]/g, '').toUpperCase()
}

function opensAt(ts: number, lang: string) {
  return new Date(ts * 1000).toLocaleString(lang, { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
}

/** Seat check-in for attendees (issue #46): where they sit, so the crew finds them fast. On a PC
 *  people type the PIN from the card at their seat and their nick: the PIN names the seat, and the
 *  PC's switch port is what Floorbit learns. A phone (the QR code) can type the seat instead. */
export default function Checkin() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const info = useQuery({
    queryKey: qk.checkinInfo, queryFn: () => get<CheckinInfo>('/api/checkin/info'),
    // While the switches are asked in the background, look again now and then.
    refetchInterval: (q) => (q.state.data?.checkin?.wired === 'pending' ? 5000 : false),
  })
  const [device] = useState(deviceClass)
  const [form, setForm] = useState<Form | null>(null)
  const [changing, setChanging] = useState(false)
  const [bySeat, setBySeat] = useState(false)
  const mine = info.data?.checkin ?? null
  const values: Form = form ?? { pin: new URLSearchParams(window.location.search).get('pin') ?? '', seat: '', username: mine?.username ?? '' }
  const withSeat = bySeat && !info.data?.pin_required
  const send = useMutation({
    mutationFn: () => post<Done & { ok: boolean }>('/api/checkin', withSeat
      ? { seat: values.seat.trim(), username: values.username.trim(), device }
      : { pin: cleanPin(values.pin), username: values.username.trim(), device }),
    onSuccess: () => { setChanging(false); void qc.invalidateQueries({ queryKey: qk.checkinInfo }) },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); send.mutate() }
  const done: Done | null = mine ?? send.data ?? null
  const notPc = device === 'mobile' || info.data?.on_pc === false

  let body
  if (info.isPending) {
    body = <Paper withBorder radius="lg" p="lg"><Loader aria-label={t('common.loading')} /></Paper>
  } else if (info.error) {
    body = (
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm" align="center" ta="center">
          <ThemeIcon size={56} radius="xl" variant="light" color="down"><IconPlugConnectedX size={30} /></ThemeIcon>
          <Title order={1} size="h3">{t('checkin.unreachable')}</Title>
          <Text c="dimmed" size="sm">{t('checkin.unreachableText')}</Text>
          <Button variant="default" onClick={() => void info.refetch()}>{t('checkin.retry')}</Button>
        </Stack>
      </Paper>
    )
  } else if (!info.data?.open) {
    body = (
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm" align="center" ta="center">
          <ThemeIcon size={56} radius="xl" variant="light" color="gray"><IconCalendarTime size={30} /></ThemeIcon>
          <Title order={1} size="h3">{t('checkin.closed')}</Title>
          <Text c="dimmed" size="sm">
            {info.data?.opens_at
              ? t('checkin.opensAt', { when: opensAt(info.data.opens_at, i18n.language) })
              : t('checkin.closedText')}
          </Text>
        </Stack>
      </Paper>
    )
  } else if (done && !changing) {
    body = (
      <Paper withBorder radius="lg" p="lg" className="fb-public-hero">
        <Stack gap="sm" align="center" ta="center">
          <ThemeIcon size={64} radius="xl" variant="light" color="up"><IconCircleCheck size={38} /></ThemeIcon>
          <Title order={1} size="h2">{t('checkin.doneTitle', { name: done.username })}</Title>
          <Text>{t('checkin.doneAt')}</Text>
          <Text fz={40} fw={700} lh={1.1} ff="var(--font-mono)" className="fb-public-done">{done.seat}</Text>
          <Text c="dimmed" size="sm">{t('checkin.doneText')}</Text>
          {done.wired && <Text size="sm" c={done.wired === 'verified' ? 'up' : 'dimmed'}>{t(`checkin.wired.${done.wired}`)}</Text>}
          <Anchor component="button" type="button" size="sm" onClick={() => { setForm({ pin: '', seat: '', username: done.username }); setChanging(true); send.reset() }}>
            {t('checkin.change')}
          </Anchor>
        </Stack>
      </Paper>
    )
  } else {
    body = (
      <Paper withBorder radius="lg" p="lg">
        <form onSubmit={submit} autoComplete="off">
          <Stack gap="md">
            <div>
              <Title order={1} size="h2">{t('checkin.title')}</Title>
              <Text c="dimmed" size="sm">{t('checkin.intro')}</Text>
            </div>
            {send.error && <Alert color="down" role="alert">{send.error.message}</Alert>}
            {notPc && <Alert color="warn">{t('checkin.onPc')}</Alert>}
            {info.data?.suggested_seat && <Text size="sm">{t('checkin.knownSeat', { seat: info.data.suggested_seat })}</Text>}
            {withSeat ? (
              <TextInput label={t('checkin.seat')} placeholder={t('checkin.seatPlaceholder')} size="md" required maxLength={16}
                autoCapitalize="characters" autoFocus value={values.seat}
                onChange={(e) => setForm({ ...values, seat: e.currentTarget.value })} />
            ) : (
              <TextInput label={t('checkin.pin')} description={t('checkin.pinHelp')} placeholder="K7M2X" size="md" required maxLength={9}
                autoCapitalize="characters" spellCheck={false} autoFocus value={values.pin}
                styles={{ input: { fontFamily: 'var(--font-mono)', letterSpacing: '0.2em', textTransform: 'uppercase' } }}
                onChange={(e) => setForm({ ...values, pin: e.currentTarget.value })} />
            )}
            <TextInput label={t('checkin.username')} placeholder={t('checkin.usernamePlaceholder')} size="md" required maxLength={48}
              value={values.username} onChange={(e) => setForm({ ...values, username: e.currentTarget.value })} />
            <Button type="submit" size="lg" fullWidth loading={send.isPending}
              disabled={!(withSeat ? values.seat.trim() : cleanPin(values.pin)) || !values.username.trim()}>
              {t('checkin.submit')}
            </Button>
            <Text c="dimmed" size="xs">{t('checkin.fromSeat')}</Text>
            {!info.data?.pin_required && (
              <Anchor component="button" type="button" size="xs" ta="left" onClick={() => { setBySeat(!bySeat); send.reset() }}>
                {withSeat ? t('checkin.usePin') : t('checkin.noPin')}
              </Anchor>
            )}
          </Stack>
        </form>
      </Paper>
    )
  }

  return (
    <PublicPage title={t('checkin.title')}>
      {body}
      {info.data?.ip && <Text c="dimmed" size="xs" ta="center">{t('checkin.ip', { ip: info.data.ip })}</Text>}
    </PublicPage>
  )
}
