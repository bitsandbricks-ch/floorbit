import { IconBell, IconSpeakerphone } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get } from '@/api/client'
import { boardName, type Board } from '@/pages/dashboards/model'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useCustomSections, useMe, usePageList, useProblems } from '@/api/queries'
import { readBoot } from '@/nav/boot'
import { inApp } from '@/nav/sections'
import { useShellNav, type MenuAction } from '@/nav/ShellNav'
import { useChecklist } from '@/pages/setup/checklist'
import { CrewNoticeEditor } from './CrewNotice'
import { GoTo } from './GoTo'
import { CrewNotify } from '@/notify/CrewNotify'
import { NotifySettings } from './NotifySettings'

/** The sidebar's parts for the shared AppShell, plus "Go to" and the account menu's dialogs. */
export function useAppNav() {
  const { t } = useTranslation()
  const path = useLocation().pathname
  const me = useMe().data
  const lead = useCan('incidents.assign')
  const listed = usePageList()
  const custom = useCustomSections()
  const qc = useQueryClient()
  // An admin changed the sidebar's own sections: everyone's sidebar follows without a reload.
  useLiveEvent('nav.changed', () => void qc.invalidateQueries({ queryKey: qk.pages, exact: true }))
  const problems = useProblems().data
  // For dashboards pinned to the sidebar: their names, in the reader's language for built-in ones.
  const boards = useQuery({ queryKey: qk.boards, queryFn: () => get<{ layouts: Board[] }>('/api/dashboards'), staleTime: 60_000 }).data
  const dashboards = useMemo(() => boards?.layouts.map((b) => ({ id: b.id, name: boardName(t, b) })), [boards, t])
  const [notify, setNotify] = useState(false)
  const [notice, setNotice] = useState(false)

  const boot = useMemo(() => {
    const b = readBoot()
    // The server's list comes with the page; the API's is the same list, for a page loaded without it.
    const user = me?.user ? { name: me.user.display_name || me.user.username, username: me.user.username, platform: !!me.user.platform } : b.user
    // The API's sections win once it answers: an admin's change shows without a reload.
    return { ...b, pages: b.pages.length ? b.pages : listed, custom: custom ?? b.custom, user, signOut: b.signOut || !!me?.enabled }
  }, [me, listed, custom])

  useInAppLinks(boot.pages)
  // Set up's progress beside its row, for the accounts that may open it (#1437).
  const steps = useChecklist(boot.pages.some((p) => p.id === 'setup')).data?.steps
  const setup = useMemo(() => (steps ? { done: steps.filter((s) => s.state === 'done' || s.state === 'skipped').length, count: steps.length } : null), [steps])

  const actions: MenuAction[] = []
  if (me?.user) actions.push({ id: 'notify', label: t('common.notify.menu'), icon: IconBell, run: () => setNotify(true) })
  if (me?.user && lead) actions.push({ id: 'notice', label: t('notice.menu'), icon: IconSpeakerphone, run: () => setNotice(true) })

  const shell = useShellNav({ boot, path, down: problems?.counts.down ?? null, look: problems?.counts.look ?? null, actions, dashboards, setup })
  const dialogs = (
    <>
      <GoTo />
      {shell.customizer}
      <CrewNotify />
      {notify && <NotifySettings opened onClose={() => setNotify(false)} />}
      {notice && <CrewNoticeEditor onClose={() => setNotice(false)} />}
    </>
  )
  return { shell, dialogs }
}

/** Plain links inside the pages (``<a href="/incidents?q=…">``) open as routes too, so the
 *  sidebar stays and only the page changes. Only for pages in the list: anything else (a
 *  download, a public page, a page this account may not open) loads as before. */
function useInAppLinks(pages: { href: string }[]) {
  const navigate = useNavigate()
  useEffect(() => {
    const listed = new Set(pages.map((p) => p.href))
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = e.target instanceof Element ? e.target.closest('a') : null
      if (!a || !a.href || (a.target && a.target !== '_self') || a.hasAttribute('download')) return
      const url = new URL(a.href, window.location.href)
      if (url.origin !== window.location.origin || !inApp(url.pathname + url.search, listed)) return
      e.preventDefault()
      navigate(url.pathname + url.search + url.hash)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [pages, navigate])
}
