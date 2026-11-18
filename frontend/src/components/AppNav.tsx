import { IconBell, IconSpeakerphone } from '@tabler/icons-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useCustomSections, useMe, usePageList, useProblems } from '@/api/queries'
import { readBoot } from '@/nav/boot'
import { GOTO_EVENT } from '@/nav/goto'
import { inApp } from '@/nav/sections'
import { Sidebar, type LinkProps, type MenuAction } from '@/nav/Sidebar'
import { CrewNoticeEditor } from './CrewNotice'
import { GoTo } from './GoTo'
import { NotifySettings } from './NotifySettings'

// Inside the React app a page is a route: the sidebar stays, only the page changes.
function RouteLink({ href, children, ...rest }: LinkProps) {
  if (!inApp(href)) return <a href={href} {...rest}>{children}</a>
  return <Link to={href} {...rest}>{children}</Link>
}
const renderLink = (p: LinkProps) => <RouteLink {...p} />


/** The sidebar, "Go to" and the account menu's dialogs for the React pages. */
export function AppNav() {
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
  const [goTo, setGoTo] = useState(false)
  const [notify, setNotify] = useState(false)
  const [notice, setNotice] = useState(false)
  const open = useCallback(() => setGoTo(true), [])
  const close = useCallback(() => setGoTo(false), [])
  useEffect(() => {
    window.addEventListener(GOTO_EVENT, open)
    return () => window.removeEventListener(GOTO_EVENT, open)
  }, [open])

  const boot = useMemo(() => {
    const b = readBoot()
    // The server's list comes with the page; the API's is the same list, for a page loaded without it.
    const user = me?.user ? { name: me.user.display_name || me.user.username, username: me.user.username, platform: !!me.user.platform } : b.user
    // The API's sections win once it answers: an admin's change shows without a reload.
    return { ...b, pages: b.pages.length ? b.pages : listed, custom: custom ?? b.custom, user, signOut: b.signOut || !!me?.enabled }
  }, [me, listed, custom])

  useInAppLinks(boot.pages)

  const actions: MenuAction[] = []
  if (me?.user) actions.push({ id: 'notify', label: t('common.notify.menu'), icon: IconBell, run: () => setNotify(true) })
  if (me?.user && lead) actions.push({ id: 'notice', label: t('notice.menu'), icon: IconSpeakerphone, run: () => setNotice(true) })

  return (
    <>
      <Sidebar boot={boot} path={path} renderLink={renderLink} onGoTo={open} down={problems?.counts.down ?? null} actions={actions} />
      <GoTo opened={goTo} onOpen={open} onClose={close} />
      {notify && <NotifySettings opened onClose={() => setNotify(false)} />}
      {notice && <CrewNoticeEditor onClose={() => setNotice(false)} />}
    </>
  )
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
