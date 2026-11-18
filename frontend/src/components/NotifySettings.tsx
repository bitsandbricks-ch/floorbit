import { Alert, Button, Checkbox, Group, Modal, Select, Stack, Switch, Text } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface NotifyPrefs {
  on: boolean; incidents: boolean; jobs: boolean; switches: boolean; services?: boolean
  quiet?: boolean; quietFrom?: string; quietTo?: string; jobsInQuiet?: boolean
  /** Seats to notify about when their link changes (issue #178). */
  watch?: string[]
}

// Quiet hours in 24-hour time: the browser's time input shows AM/PM to English browsers.
const HALF_HOURS = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, '0')}:${i % 2 ? '30' : '00'}`)
const halfHours = (current: string) => (HALF_HOURS.includes(current) ? HALF_HOURS : [...HALF_HOURS, current].sort())

declare global {
  interface Window {
    floorNotify?: {
      supported: () => boolean
      settings: () => NotifyPrefs
      permission: () => NotificationPermission | 'unsupported'
      quietNow?: () => boolean
      set: (changes: Partial<NotifyPrefs>) => Promise<NotifyPrefs>
    }
  }
}

/** Browser notifications for this device (issue #154). static/js/notify.js does the work; this is
 *  only its settings, so the editor (plain JS) and the React pages share one switch. */
export function NotifySettings({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const api = typeof window !== 'undefined' ? window.floorNotify : undefined
  const [prefs, setPrefs] = useState<NotifyPrefs | null>(() => api?.settings() ?? null)
  const [permission, setPermission] = useState(() => api?.permission() ?? 'unsupported')
  const change = async (changes: Partial<NotifyPrefs>) => {
    if (!api) return
    setPrefs(await api.set(changes))
    setPermission(api.permission())
  }
  return (
    <Modal opened={opened} onClose={onClose} title={t('common.notify.title')} closeButtonProps={{ 'aria-label': t('goto.close') }}>
      {!api || !api.supported() || !prefs ? (
        <Text>{t('common.notify.unsupported')}</Text>
      ) : (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{t('common.notify.intro')}</Text>
          <Switch label={t('common.notify.on')} checked={prefs.on} onChange={(e) => void change({ on: e.currentTarget.checked })} />
          {permission === 'denied' && <Alert color="warn">{t('common.notify.denied')}</Alert>}
          <Checkbox label={t('common.notify.jobs')} checked={prefs.jobs} disabled={!prefs.on} onChange={(e) => void change({ jobs: e.currentTarget.checked })} />
          <Checkbox label={t('common.notify.incidents')} checked={prefs.incidents} disabled={!prefs.on} onChange={(e) => void change({ incidents: e.currentTarget.checked })} />
          <Checkbox label={t('common.notify.switches')} checked={prefs.switches} disabled={!prefs.on} onChange={(e) => void change({ switches: e.currentTarget.checked })} />
          <Checkbox label={t('common.notify.services')} checked={prefs.services !== false} disabled={!prefs.on} onChange={(e) => void change({ services: e.currentTarget.checked })} />
          <Checkbox label={t('common.notify.quiet')} checked={!!prefs.quiet} disabled={!prefs.on} onChange={(e) => void change({ quiet: e.currentTarget.checked })} />
          {prefs.on && prefs.quiet && (
            <Stack gap="xs" pl="xl">
              <Group gap="sm" wrap="nowrap">
                <Select w={130} label={t('common.notify.quietFrom')} value={prefs.quietFrom ?? '22:00'} allowDeselect={false}
                  data={halfHours(prefs.quietFrom ?? '22:00')} onChange={(v) => { if (v) void change({ quietFrom: v }) }} />
                <Select w={130} label={t('common.notify.quietTo')} value={prefs.quietTo ?? '08:00'} allowDeselect={false}
                  data={halfHours(prefs.quietTo ?? '08:00')} onChange={(v) => { if (v) void change({ quietTo: v }) }} />
              </Group>
              <Checkbox label={t('common.notify.jobsInQuiet')} checked={prefs.jobsInQuiet !== false} onChange={(e) => void change({ jobsInQuiet: e.currentTarget.checked })} />
              {api.quietNow?.() && (
                <Text size="sm" c="dimmed">{t(prefs.jobsInQuiet !== false ? 'common.notify.quietNow' : 'common.notify.quietNowAll')}</Text>
              )}
            </Stack>
          )}
          <Group justify="flex-end"><Button variant="default" onClick={onClose}>{t('common.notify.done')}</Button></Group>
        </Stack>
      )}
    </Modal>
  )
}
