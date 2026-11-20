import { Button, Group, Modal, Popover, SegmentedControl, Select, Stack, Text, Textarea } from '@mantine/core'
import { IconAlertTriangle, IconSpeakerphone } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useNotice } from '@/api/queries'
import type { CrewNotice } from '@/api/types'
import { clock } from '@/lib/time'

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
  return clock(ts, lang)
}

function hide(at: number) {
  try {
    localStorage.setItem(HIDDEN_KEY, String(at))
  } catch {
    /* private mode: hidden for this page only */
  }
}

/** The crew notice as a badge in the top bar (issue #1006): coloured by its level while it is
 *  new, quiet once this person hid it, and a new notice lights it again. The full text, who put
 *  it up and, for leads, Change and Take down open from it. */
export function CrewNoticeBadge({ compact }: { compact?: boolean }) {
  const { t, i18n } = useTranslation()
  const notice = useNotice().data?.notice
  const lead = useCan('incidents.assign')
  const client = useQueryClient()
  const [hidden, setHidden] = useState(hiddenAt)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const remove = useMutation({
    mutationFn: () => del<{ notice: null }>('/api/notice'),
    onSuccess: (data) => { client.setQueryData(qk.notice, data); setOpen(false) },
  })
  if (!notice) return null
  const quiet = hidden === notice.at
  const warn = notice.level === 'warn'
  const Icon = warn ? IconAlertTriangle : IconSpeakerphone
  const tone = quiet ? 'is-quiet' : warn ? 'is-warn' : 'is-info'
  const when = notice.by ? t('notice.by', { name: notice.by, time: time(notice.at, i18n.language) }) : time(notice.at, i18n.language)
  return (
    <>
      <Popover opened={open} onChange={setOpen} position="bottom-end" width={340} shadow="md" withArrow>
        <Popover.Target>
          <button type="button" className={`fb-notice-badge ${tone}${compact ? ' is-compact' : ''}`} onClick={() => setOpen((o) => !o)}
            aria-label={`${t('notice.title')}: ${notice.text}`} aria-expanded={open} title={compact ? notice.text : undefined}>
            <Icon size={15} aria-hidden="true" />
            {!compact && <span className="fb-notice-badge-text" aria-hidden="true">{notice.text}</span>}
          </button>
        </Popover.Target>
        <Popover.Dropdown>
          <Stack gap="xs">
            <Group gap={6} c={warn ? 'warn' : 'trace'}>
              <Icon size={16} aria-hidden="true" />
              <Text size="sm" fw={600}>{t('notice.title')}</Text>
            </Group>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{notice.text}</Text>
            <Text size="xs" c="dimmed">
              {when}{notice.until ? ` · ${t('notice.until', { time: time(notice.until, i18n.language) })}` : ''}
            </Text>
            <Group gap="xs" justify="flex-end">
              {!quiet && (
                <Button size="compact-sm" variant="default" onClick={() => { hide(notice.at); setHidden(notice.at); setOpen(false) }}>
                  {t('notice.markRead')}
                </Button>
              )}
              {lead && (
                <>
                  <Button size="compact-sm" variant="default" onClick={() => { setOpen(false); setEditing(true) }}>{t('notice.change')}</Button>
                  <Button size="compact-sm" variant="subtle" color="down" loading={remove.isPending} onClick={() => remove.mutate()}>
                    {t('notice.takeDown')}
                  </Button>
                </>
              )}
            </Group>
            {remove.error && <Text c="down" size="xs" role="alert">{remove.error.message}</Text>}
          </Stack>
        </Popover.Dropdown>
      </Popover>
      {editing && <CrewNoticeEditor onClose={() => setEditing(false)} />}
    </>
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
