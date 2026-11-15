import { Button, Kbd, Modal, TextInput } from '@mantine/core'
import { useHotkeys } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { usePageList, usePlaces } from '@/api/queries'
import { useLocation } from 'react-router-dom'
import { fold, RECENT_MAX, recentPages } from './pages'

/** "Go to" button in every React page's header, and Ctrl+K / ⌘K, to jump to any page
 *  without the detour through the floor plan (issue #242). */
export function GoTo() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // Mantine's mod+K: Ctrl on Windows and Linux, ⌘ on a Mac.
  useHotkeys([['mod+K', () => setOpen(true)]], [])
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <>
      <Button
        variant="subtle" color="gray" leftSection={<IconSearch size={16} aria-hidden="true" />}
        onClick={() => setOpen(true)} aria-keyshortcuts="Control+K Meta+K"
        rightSection={<Kbd size="xs" visibleFrom="sm">{mac ? '⌘K' : 'Ctrl K'}</Kbd>}
      >
        <span className="fb-goto-label">{t('goto.button')}</span>
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title={t('goto.title')} size="md" closeButtonProps={{ 'aria-label': t('goto.close') }}
        // Room for the search box's focus ring under the sticky title.
        styles={{ body: { paddingTop: 4 } }}
      >
        {open && <Palette onDone={() => setOpen(false)} />}
      </Modal>
    </>
  )
}

function Palette({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
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

  const shown = useMemo(() => {
    const q = fold(query.trim())
    const recent = recentPages().filter((href) => href !== here && pages.some((p) => p.href === href)).slice(0, RECENT_MAX)
    // The server's English label stands in for a page this version has no translation for yet.
    const named = pages.map((p) => ({ ...p, label: t(`goto.pages.${p.id}`, { defaultValue: p.label }), recent: recent.includes(p.href) }))
    // Nothing typed yet: the pages opened last come first, newest on top (issue #244).
    if (!q) return [...named.filter((p) => p.recent).sort((a, b) => recent.indexOf(a.href) - recent.indexOf(b.href)), ...named.filter((p) => !p.recent)]
    // Label first, then the path, so "set" finds Settings before /settings/... pages named otherwise.
    const found = named
      .filter((p) => fold(p.label).includes(q) || p.href.includes(q))
      .sort((a, b) => Number(!fold(a.label).includes(q)) - Number(!fold(b.label).includes(q)))
    // Then the seats and switches the server found (issue #252), once it answered for this text.
    const spots = asked === query ? places.map((p) => ({ href: p.href, id: p.kind, label: `${t(`goto.${p.kind}`)} ${p.name}`, recent: false })) : []
    return [...found, ...spots]
  }, [pages, query, t, here, places, asked])
  const current = Math.min(active, shown.length - 1)

  // A full page load: the floor plan and the settings pages are server pages, not routes.
  const go = (href: string) => {
    onDone()
    window.location.assign(href)
  }
  const move = (to: number) => {
    setActive(to)
    list.current?.children[to]?.scrollIntoView?.({ block: 'nearest' })
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!shown.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); move((current + 1) % shown.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move((current - 1 + shown.length) % shown.length) }
    else if (e.key === 'Enter') { e.preventDefault(); go(shown[current].href) }
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
              className="fb-goto-item" onMouseEnter={() => setActive(i)} onClick={() => go(p.href)}
            >
              <span>
                {p.label}
                {p.recent && !query.trim() && <span className="fb-goto-recent"> · {t('goto.recent')}</span>}
              </span>
              <span className="fb-goto-path">{p.href}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="fb-goto-empty">{t('goto.none')}</p>
      )}
    </>
  )
}
