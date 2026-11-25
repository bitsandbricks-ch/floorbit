import { Button, Group, Modal, Text } from '@mantine/core'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useGuarded, wouldLose } from './useLeaveWarning'

/** Asks before a link inside the app leaves a page with unsaved changes (#993). The app runs on
 *  BrowserRouter, which has no navigation blocker, so this watches clicks on links: before React
 *  sees them, only while a page has something unsaved (useLeaveWarning). Mounted once, in App. */
export function LeaveGuard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const guarded = useGuarded()
  const [to, setTo] = useState<string | null>(null)

  useEffect(() => {
    if (!guarded) return
    const click = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return
      const url = new URL(a.href, window.location.href)
      if (url.origin !== window.location.origin || !wouldLose(url.pathname)) return
      e.preventDefault()
      e.stopPropagation()
      setTo(url.pathname + url.search + url.hash)
    }
    document.addEventListener('click', click, true)
    return () => document.removeEventListener('click', click, true)
  }, [guarded])

  return (
    <Modal opened={to !== null} onClose={() => setTo(null)} title={t('common.leave.title')} centered>
      <Text size="sm">{t('common.leave.text')}</Text>
      <Group justify="flex-end" mt="md">
        <Button variant="default" onClick={() => setTo(null)} data-autofocus>{t('common.leave.stay')}</Button>
        <Button color="down" onClick={() => { const go = to; setTo(null); if (go) navigate(go) }}>{t('common.leave.go')}</Button>
      </Group>
    </Modal>
  )
}
