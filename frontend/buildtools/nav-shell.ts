// The sidebar's first paint on the pages Flask draws (templates/_nav.html): the build writes the
// icons, the order and the texts to static/app/nav-shell.json, Flask draws the same markup as
// Sidebar.tsx from it, and the script takes over that markup when it runs. So the sidebar is
// there in the first paint, before the floor plan, and never pops in after it.
import { IconChevronDown, IconDots, IconLayoutSidebarLeftCollapse, IconLayoutSidebarLeftExpand, IconMenu2, IconSearch } from '@tabler/icons-react'
import { readFileSync } from 'fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { PINNED, SECTIONS, pageIcon, sectionIcon } from '../src/nav/sections'
import type { Icon } from '@tabler/icons-react'

const svg = (icon: Icon, size: number, className?: string) =>
  renderToStaticMarkup(createElement(icon, { size, className, 'aria-hidden': 'true' }))

/** The texts the sidebar shows, per language, from src/i18n (nav.json and goto.json's pages). */
function texts(dir: string, lang: string) {
  const read = (name: string) => JSON.parse(readFileSync(`${dir}/${lang}/${name}.json`, 'utf8')) as Record<string, unknown>
  const nav = read('nav')
  const goto = read('goto') as { pages?: Record<string, string> }
  const common = read('common') as { signedInAs?: string }
  return { nav, pages: goto.pages ?? {}, signedInAs: common.signedInAs ?? 'Signed in as {{username}}' }
}

export function navShell(i18nDir: string) {
  const ids = [...PINNED, ...SECTIONS.flatMap((s) => s.pages)]
  return {
    pinned: PINNED,
    tabs: ['floorPlan', 'seats', 'problems', 'incidents'],
    sections: SECTIONS.map((s) => ({ id: s.id, pages: s.pages })),
    icons: {
      // Rows: 18 px in the sidebar; the phone bar uses 22 px.
      page: Object.fromEntries([...ids, '*'].map((id) => [id, svg(pageIcon(id), 18, 'fb-nav-icon')])),
      tab: Object.fromEntries([...ids, '*'].map((id) => [id, svg(pageIcon(id), 22)])),
      section: Object.fromEntries([...SECTIONS.map((s) => s.id), 'more' as const].map((id) => [id, svg(sectionIcon(id), 18, 'fb-nav-icon')])),
      search: svg(IconSearch, 18, 'fb-nav-icon'),
      chevron: svg(IconChevronDown, 14, 'fb-nav-chevron'),
      collapse: svg(IconLayoutSidebarLeftCollapse, 18),
      expand: svg(IconLayoutSidebarLeftExpand, 18),
      menu: svg(IconMenu2, 22),
      dots: svg(IconDots, 16),
    },
    texts: Object.fromEntries(['en', 'de-CH'].map((lang) => [lang, texts(i18nDir, lang)])),
  }
}
