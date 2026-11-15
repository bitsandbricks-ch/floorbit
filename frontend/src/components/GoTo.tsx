import { Button, Kbd, Modal, TextInput } from '@mantine/core'
import { useHotkeys } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useFeaturesOff, useMe } from '@/api/queries'
import { fold, PAGES, type PageLink } from './pages'

/** The pages this account may open with the features that are on. */
function usePages(): PageLink[] {
  const off = useFeaturesOff()
  const me = useMe().data
  return PAGES.filter((p) => {
    if (p.feature && off.includes(p.feature)) return false
    if (!p.can || !me || !me.enabled) return true
    return !!me.user?.permissions?.includes(p.can)
  })
}

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
  const pages = usePages()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const listId = useId()
  const list = useRef<HTMLUListElement>(null)

  const shown = useMemo(() => {
    const q = fold(query.trim())
    const named = pages.map((p) => ({ ...p, label: t(`goto.pages.${p.id}`) }))
    if (!q) return named
    // Label first, then the path, so "set" finds Settings before /settings/... pages named otherwise.
    return named
      .filter((p) => fold(p.label).includes(q) || p.href.includes(q))
      .sort((a, b) => Number(!fold(a.label).includes(q)) - Number(!fold(b.label).includes(q)))
  }, [pages, query, t])
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
              <span>{p.label}</span>
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
