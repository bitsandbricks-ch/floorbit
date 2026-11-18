import { Modal, TextInput } from '@mantine/core'
import { useHotkeys } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useCan, useMe, usePageList, usePlaces } from '@/api/queries'
import { toggleScheme, useScheme } from '@/colorScheme'
import { useLocation, useNavigate } from 'react-router-dom'
import { isPluginPage, isServerPage } from '@/nav/sections'
import { CrewNoticeEditor } from './CrewNotice'
import { NotifySettings } from './NotifySettings'
import { fold, RECENT_MAX, recentPages } from './pages'
import { signOut } from './signOut'

/** A dialog an action opens once the palette has closed (issue #254). */
type Opens = 'notice' | 'notify'

interface Item { href: string; id: string; label: string; recent: boolean; run?: () => void }

/** "Go to" (Ctrl+K / ⌘K) on every React page: jump to any page, seat or switch without the
 *  detour through the floor plan (issue #242). The sidebar's search row opens it too. */
export function GoTo({ opened, onOpen, onClose }: { opened: boolean; onOpen: () => void; onClose: () => void }) {
  const { t } = useTranslation()
  const [opens, setOpens] = useState<Opens | null>(null)
  // Mantine's mod+K: Ctrl on Windows and Linux, ⌘ on a Mac.
  useHotkeys([['mod+K', onOpen]], [])
  return (
    <>
      <Modal opened={opened} onClose={onClose} title={t('goto.title')} size="md" closeButtonProps={{ 'aria-label': t('goto.close') }}
        // Room for the search box's focus ring under the sticky title.
        styles={{ body: { paddingTop: 4 } }}
      >
        {opened && <Palette onDone={onClose} onOpen={(o) => { onClose(); setOpens(o) }} />}
      </Modal>
      {opens === 'notice' && <CrewNoticeEditor onClose={() => setOpens(null)} />}
      {opens === 'notify' && <NotifySettings opened onClose={() => setOpens(null)} />}
    </>
  )
}

/** What the palette can do besides opening a page (issue #254): the user menu's entries, typed. */
function useActions(onDone: () => void, onOpen: (o: Opens) => void) {
  const { t } = useTranslation()
  const me = useMe().data
  const lead = useCan('incidents.assign')
  const scheme = useScheme()
  const toggle = toggleScheme()
  const out: { id: string; label: string; run: () => void }[] = []
  if (toggle) out.push({ id: 'theme', label: scheme === 'light' ? t('common.themeDark') : t('common.themeLight'), run: () => { toggle(); onDone() } })
  if (me?.user) out.push({ id: 'notify', label: t('goto.actions.notify'), run: () => onOpen('notify') })
  if (me?.user && lead) out.push({ id: 'notice', label: t('goto.actions.notice'), run: () => onOpen('notice') })
  if (me?.enabled && me.user) out.push({ id: 'signOut', label: t('common.signOut'), run: signOut })
  return out
}

function Palette({ onDone, onOpen }: { onDone: () => void; onOpen: (o: Opens) => void }) {
  const { t } = useTranslation()
  const actions = useActions(onDone, onOpen)
  const pages = usePageList()
  const here = useLocation().pathname
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  // Ask the server for seats and switches once typing pauses, not on every key.
  const [asked, setAsked] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setAsked(query), 150)
    return () => clearTimeout(timer)
  }, [query])
  const places = usePlaces(asked)
  const listId = useId()
  const list = useRef<HTMLUListElement>(null)

  const shown = useMemo((): Item[] => {
    const q = fold(query.trim())
    const recent = recentPages().filter((href) => href !== here && pages.some((p) => p.href === href)).slice(0, RECENT_MAX)
    // The server's English label stands in for a page this version has no translation for yet.
    const named = pages.map((p) => ({ ...p, label: isPluginPage(p.id) ? p.label : t(`goto.pages.${p.id}`, { defaultValue: p.label }), recent: recent.includes(p.href) }))
    // Other words people type for a page ("Strom" for Electrics, "DHCP" for Security), in both
    // languages, so the English word works in German too.
    const also = (id: string) => fold(`${t(`goto.also.${id}`, { defaultValue: '' })} ${t(`goto.also.${id}`, { lng: 'en', defaultValue: '' })}`)
    // Nothing typed yet: the pages opened last come first, newest on top (issue #244).
    if (!q) return [...named.filter((p) => p.recent).sort((a, b) => recent.indexOf(a.href) - recent.indexOf(b.href)), ...named.filter((p) => !p.recent)]
    // Label first, then the path, so "set" finds Settings before /settings/... pages named otherwise.
    const found = named
      .filter((p) => fold(p.label).includes(q) || p.href.includes(q) || also(p.id).includes(q))
      .sort((a, b) => Number(!fold(a.label).includes(q)) - Number(!fold(b.label).includes(q)))
    // Then the seats and switches the server found (issue #252), once it answered for this text.
    const spots = asked === query ? places.map((p) => ({ href: p.href, id: p.kind, label: `${t(`goto.${p.kind}`)} ${p.name}`, recent: false })) : []
    // Actions only once typed, so the list without text stays a list of pages.
    const doable = actions.filter((a) => fold(a.label).includes(q)).map((a) => ({ href: `#${a.id}`, id: a.id, label: a.label, recent: false, run: a.run }))
    return [...found, ...doable, ...spots]
  }, [pages, query, t, here, places, asked, actions])
  const current = Math.min(active, shown.length - 1)

  const navigate = useNavigate()
  // The floor plan and the settings pages are server pages: a full page load. The rest are routes.
  const pick = (item: Item) => {
    if (item.run) item.run()
    else go(item.href)
  }
  const go = (href: string) => {
    onDone()
    if (isServerPage(href)) window.location.assign(href)
    else navigate(href)
  }
  const move = (to: number) => {
    setActive(to)
    list.current?.children[to]?.scrollIntoView?.({ block: 'nearest' })
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!shown.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); move((current + 1) % shown.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move((current - 1 + shown.length) % shown.length) }
    else if (e.key === 'Enter') { e.preventDefault(); pick(shown[current]) }
  }

  return (
    <>
      <TextInput
        data-autofocus
        placeholder={t('goto.placeholder')}
        aria-label={t('goto.placeholder')}
        value={query}
        onChange={(e) => { setQuery(e.currentTarget.value); setActive(0) }}
        onKeyDown={onKey}
        role="combobox"
        aria-expanded="true"
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={shown.length ? `${listId}-${current}` : undefined}
        leftSection={<IconSearch size={16} aria-hidden="true" />}
      />
      {shown.length ? (
        <ul ref={list} id={listId} role="listbox" aria-label={t('goto.title')} className="fb-goto-list">
          {shown.map((p, i) => (
            <li
              key={p.href} id={`${listId}-${i}`} role="option" aria-selected={i === current}
              className="fb-goto-item" onMouseEnter={() => setActive(i)} onClick={() => pick(p)}
            >
              <span>
                {p.label}
                {p.recent && !query.trim() && <span className="fb-goto-recent"> · {t('goto.recent')}</span>}
              </span>
              <span className="fb-goto-path">{p.run ? t('goto.action') : p.href}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="fb-goto-empty">{t('goto.none')}</p>
      )}
    </>
  )
}
