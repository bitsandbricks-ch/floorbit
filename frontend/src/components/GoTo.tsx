import { CommandPalette, createCommandPalette, type PaletteGroup, type PaletteItem } from '@bitsandbricks/ui/spotlight'
import '@mantine/spotlight/styles.css'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useMe, usePageList } from '@/api/queries'
import type { Place } from '@/api/types'
import { toggleScheme, useScheme } from '@/colorScheme'
import { GOTO_EVENT } from '@/nav/goto'
import { isPluginPage, isServerPage } from '@/nav/sections'
import { CrewNoticeEditor } from './CrewNotice'
import { NotifySettings } from './NotifySettings'
import { fold, RECENT_MAX, recentPages } from './pages'
import { signOut } from './signOut'

const [store, palette] = createCommandPalette()

/** A dialog an action opens once the palette has closed (issue #254). */
type Opens = 'notice' | 'notify'

/** Every page fits in its group: Floorbit lists them all while nothing is typed. */
const LIMIT = 60

/** "Go to" (Ctrl+K / ⌘K, or "/") on every React page, the shared CommandPalette: jump to any page,
 *  seat, switch or player without the detour through the floor plan (issues #242, #252), or do what
 *  the user menu does (#254). The sidebar's search row and the top bar open it too (GOTO_EVENT). */
export function GoTo() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const here = useLocation().pathname
  const me = useMe().data
  const lead = useCan('incidents.assign')
  const scheme = useScheme()
  const toggle = toggleScheme()
  const pages = usePageList()
  const [opens, setOpens] = useState<Opens | null>(null)

  useEffect(() => {
    const open = () => palette.open()
    window.addEventListener(GOTO_EVENT, open)
    return () => window.removeEventListener(GOTO_EVENT, open)
  }, [])

  // The server's English label stands in for a page this version has no translation for yet.
  const label = (id: string, fallback: string) => (isPluginPage(id) ? fallback : t(`goto.pages.${id}`, { defaultValue: fallback }))
  // Other words people type for a page ("Strom" for Electrics, "DHCP" for Security), in both
  // languages so the English word works in German too, and the name without accents ("ubergabe").
  const also = (id: string, name: string) => [
    t(`goto.also.${id}`, { defaultValue: '' }), t(`goto.also.${id}`, { lng: 'en', defaultValue: '' }), fold(name),
  ].filter(Boolean)
  const items: PaletteItem[] = pages.map((p) => {
    const name = label(p.id, p.label)
    return { id: p.href, label: name, description: p.href, keywords: also(p.id, name), href: p.href }
  })
  // The pages opened last, newest first, but not the one you are on.
  const recent = recentPages().filter((href) => href !== here)
    .map((href) => items.find((it) => it.href === href)).filter((it): it is PaletteItem => !!it).slice(0, RECENT_MAX)

  const actions: PaletteItem[] = []
  if (toggle) actions.push({ id: 'theme', label: scheme === 'light' ? t('common.themeDark') : t('common.themeLight'), onSelect: toggle })
  if (me?.user) actions.push({ id: 'notify', label: t('goto.actions.notify'), onSelect: () => setOpens('notify') })
  if (me?.user && lead) actions.push({ id: 'notice', label: t('goto.actions.notice'), onSelect: () => setOpens('notice') })
  if (me?.enabled && me.user) actions.push({ id: 'signOut', label: t('common.signOut'), onSelect: signOut })

  const groups: PaletteGroup[] = [
    { id: 'pages', label: t('goto.groups.pages'), items },
    { id: 'actions', label: t('goto.groups.actions'), items: actions, commands: true },
  ]

  // Seats, switches and players the server finds (issue #252), from the same cache as before.
  const search = useCallback(async (q: string): Promise<PaletteGroup[]> => {
    const { places } = await client.fetchQuery({
      queryKey: qk.places(q), queryFn: () => get<{ places: Place[] }>(`/api/pages/find?q=${encodeURIComponent(q)}`), staleTime: 30_000,
    })
    return [{ id: 'places', label: t('goto.groups.places'), items: places.map((p) => ({
      id: `${p.kind}:${p.href}:${p.name}`, label: `${t(`goto.${p.kind}`)} ${p.name}`, href: p.href,
    })) }]
  }, [client, t])

  // The floor plan and the settings pages are server pages: a full page load. The rest are routes.
  const go = (href: string) => (isServerPage(href) ? window.location.assign(href) : navigate(href))

  return (
    <>
      <CommandPalette store={store} groups={groups} recent={recent} search={search} debounce={150}
        onNavigate={go} limit={LIMIT} placeholder={t('goto.placeholder')} />
      {opens === 'notice' && <CrewNoticeEditor onClose={() => setOpens(null)} />}
      {opens === 'notify' && <NotifySettings opened onClose={() => setOpens(null)} />}
    </>
  )
}
