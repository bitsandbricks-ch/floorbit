import { Alert, Anchor, Button, Loader, Paper, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { IconCalendarTime, IconCircleCheck, IconPlugConnectedX } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { CheckinInfo } from '@/api/types'
import { PublicPage } from '@/components/PublicPage'

type Done = { seat: string; username: string }

function opensAt(ts: number, lang: string) {
  return new Date(ts * 1000).toLocaleString(lang, { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
}

/** Seat check-in for attendees (issue #46): where they sit, so the crew finds them fast. Phones
 *  first: most people open it from the QR code on their table, then check in from their PC. */
export default function Checkin() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const info = useQuery({ queryKey: qk.checkinInfo, queryFn: () => get<CheckinInfo>('/api/checkin/info') })
  const [form, setForm] = useState<{ seat: string; username: string } | null>(null)
  const [changing, setChanging] = useState(false)
  const mine = info.data?.checkin ?? null
  const values = form ?? { seat: mine?.seat ?? '', username: mine?.username ?? '' }
  const send = useMutation({
    mutationFn: () => post<Done & { ok: boolean }>('/api/checkin', { seat: values.seat.trim(), username: values.username.trim() }),
    onSuccess: () => { setChanging(false); void qc.invalidateQueries({ queryKey: qk.checkinInfo }) },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); send.mutate() }
  const done: Done | null = send.data ?? mine

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
          <Anchor component="button" type="button" size="sm" onClick={() => { setForm(done); setChanging(true); send.reset() }}>
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
            <TextInput label={t('checkin.seat')} placeholder={t('checkin.seatPlaceholder')} size="md" required maxLength={16}
              autoCapitalize="characters" autoFocus value={values.seat}
              onChange={(e) => setForm({ ...values, seat: e.currentTarget.value })} />
            <TextInput label={t('checkin.username')} placeholder={t('checkin.usernamePlaceholder')} size="md" required maxLength={48}
              value={values.username} onChange={(e) => setForm({ ...values, username: e.currentTarget.value })} />
            <Button type="submit" size="lg" fullWidth loading={send.isPending}
              disabled={!values.seat.trim() || !values.username.trim()}>
              {t('checkin.submit')}
            </Button>
            <Text c="dimmed" size="xs">{t('checkin.fromSeat')}</Text>
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
