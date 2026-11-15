import { Alert, Button, CloseButton, Group, Modal, SegmentedControl, Select, Stack, Text, Textarea } from '@mantine/core'
import { IconAlertTriangle, IconSpeakerphone } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useNotice } from '@/api/queries'
import type { CrewNotice } from '@/api/types'

const HIDDEN_KEY = 'floorbit-notice-hidden'
const MAX = 280

function hiddenAt(): number | null {
  try {
    return Number(localStorage.getItem(HIDDEN_KEY)) || null
  } catch {
    return null
  }
}

function time(ts: number, lang: string) {
  return new Date(ts * 1000).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
}

/** The banner under the page header. Each person can hide it; a new notice shows again. */
export function CrewNoticeBanner() {
  const { t, i18n } = useTranslation()
  const notice = useNotice().data?.notice
  const [hidden, setHidden] = useState(hiddenAt)
  if (!notice || hidden === notice.at) return null
  const hide = () => {
    try {
      localStorage.setItem(HIDDEN_KEY, String(notice.at))
    } catch {
      /* private mode: hidden for this page only */
    }
    setHidden(notice.at)
  }
  const warn = notice.level === 'warn'
  return (
    <Alert
      role="status" className="fb-notice" radius={0} color={warn ? 'warn' : 'trace'}
      icon={warn ? <IconAlertTriangle size={18} aria-hidden="true" /> : <IconSpeakerphone size={18} aria-hidden="true" />}
      title={t('notice.title')}
      withCloseButton={false}
    >
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{notice.text}</Text>
          <Text size="xs" c="dimmed">
            {notice.by ? t('notice.by', { name: notice.by, time: time(notice.at, i18n.language) }) : time(notice.at, i18n.language)}
            {notice.until ? ` · ${t('notice.until', { time: time(notice.until, i18n.language) })}` : ''}
          </Text>
        </div>
        <CloseButton aria-label={t('notice.hide')} onClick={hide} size="sm" />
      </Group>
    </Alert>
  )
}

const HOURS = ['0', '1', '2', '4', '8', '24']

/** Leads put up or take down the notice (incidents.assign; the server checks it too). */
export function CrewNoticeEditor({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const current = useNotice().data?.notice
  const [text, setText] = useState(current?.text ?? '')
  const [level, setLevel] = useState<string>(current?.level ?? 'info')
  const [hours, setHours] = useState<string>('0')
  const done = (data: { notice: CrewNotice | null }) => {
    client.setQueryData(qk.notice, data)
    onClose()
  }
  const save = useMutation({
    mutationFn: () => put<{ notice: CrewNotice }>('/api/notice', { text, level, hours: Number(hours) }),
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: () => del<{ notice: null }>('/api/notice'), onSuccess: done })
  const error = save.error ?? remove.error
  return (
    <Modal opened onClose={onClose} title={t('notice.editTitle')} closeButtonProps={{ 'aria-label': t('goto.close') }}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('notice.intro')}</Text>
        <Textarea
          label={t('notice.text')} required autosize minRows={2} maxLength={MAX} data-autofocus
          value={text} onChange={(e) => setText(e.currentTarget.value)}
          description={t('notice.left', { count: MAX - text.length })}
        />
        <div>
          <Text size="sm" fw={500} id="fb-notice-level">{t('notice.level')}</Text>
          <SegmentedControl
            aria-labelledby="fb-notice-level" value={level} onChange={setLevel}
            data={[{ value: 'info', label: t('notice.info') }, { value: 'warn', label: t('notice.warn') }]}
          />
        </div>
        <Select
          label={t('notice.for')} value={hours} onChange={(v) => setHours(v ?? '0')} allowDeselect={false}
          data={HOURS.map((h) => ({ value: h, label: h === '0' ? t('notice.untilCleared') : t('notice.hours', { count: Number(h) }) }))}
        />
        {error && <Text c="red" size="sm" role="alert">{error.message}</Text>}
        <Group justify="space-between">
          {current
            ? <Button variant="subtle" color="red" onClick={() => remove.mutate()} loading={remove.isPending}>{t('notice.takeDown')}</Button>
            : <span />}
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!text.trim()}>{t('notice.post')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
