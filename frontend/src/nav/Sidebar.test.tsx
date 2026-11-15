import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import '@/i18n'
import type { NavBoot } from './boot'
import { activeHref, group, isServerPage } from './sections'
import { Sidebar, type LinkProps } from './Sidebar'

const pages = [
  { href: '/', id: 'floorPlan', label: 'Floor plan' },
  { href: '/problems', id: 'problems', label: 'Problems' },
  { href: '/incidents', id: 'incidents', label: 'Incidents' },
  { href: '/stats', id: 'stats', label: 'Stats' },
  { href: '/traffic', id: 'traffic', label: 'Traffic' },
  { href: '/settings', id: 'settings', label: 'Settings' },
  { href: '/settings/agents', id: 'agents', label: 'Local agents' },
  { href: '/brand-new', id: 'brandNew', label: 'Brand new page' },
]
const boot: NavBoot = { pages, brand: { logo: null, name: null }, user: { name: 'Kim', username: 'kim' }, signOut: true }
const link = ({ children, ...rest }: LinkProps) => <a {...rest}>{children}</a>

function sidebar(path = '/problems', extra: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  return render(<Sidebar boot={boot} path={path} renderLink={link} onGoTo={() => {}} {...extra} />)
}
const main = () => screen.getByRole('navigation', { name: 'Main' })

afterEach(() => {
  localStorage.clear()
  document.cookie = 'floorbit_nav=; max-age=0; path=/'
})

describe('sections', () => {
  it('pins the everyday pages and folds the rest into sections, a new page into "more"', () => {
    const g = group(pages)
    expect(g.pinned.map((p) => p.id)).toEqual(['floorPlan', 'problems', 'incidents'])
    expect(g.sections.map((s) => [s.id, s.pages.map((p) => p.id)])).toEqual([
      ['network', ['stats', 'traffic']], ['admin', ['settings', 'agents']], ['more', ['brandNew']],
    ])
  })

  it('lights one row: the longest page that holds the path', () => {
    expect(activeHref(pages, '/incidents/qr')).toBe('/incidents')
    expect(activeHref(pages, '/settings/agents')).toBe('/settings/agents')
    expect(activeHref(pages, '/nowhere')).toBeNull()
  })

  it('knows which pages Flask draws', () => {
    expect(isServerPage('/')).toBe(true)
    expect(isServerPage('/settings/users')).toBe(true)
    expect(isServerPage('/settings/plugins')).toBe(false)
    expect(isServerPage('/plan?seat=B-8')).toBe(false)
  })
})

describe('Sidebar', () => {
  it('marks the page on screen and shows how many switches are down', () => {
    sidebar('/problems', { down: 3 })
    const row = within(main()).getByRole('link', { name: /Problems/ })
    expect(row).toHaveAttribute('aria-current', 'page')
    expect(row).toHaveTextContent('3 down')
  })

  it('opens the section of the page on screen, and others on a click', () => {
    sidebar('/traffic')
    expect(within(main()).getByRole('link', { name: 'Traffic' })).toHaveAttribute('aria-current', 'page')
    const admin = within(main()).getByRole('button', { name: 'Settings' })
    expect(admin).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(admin)
    expect(admin).toHaveAttribute('aria-expanded', 'true')
    expect(within(main()).getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('floorbit-nav-open')!)).toEqual(['admin'])
  })

  it('folds to icons, keeps that in a cookie, and lists a section in a flyout', () => {
    sidebar('/problems')
    fireEvent.click(within(main()).getByRole('button', { name: 'Collapse the sidebar' }))
    expect(main()).toHaveAttribute('data-state', 'rail')
    expect(document.cookie).toContain('floorbit_nav=rail')
    fireEvent.click(within(main()).getByRole('button', { name: 'Network' }))
    expect(within(main()).getByText('Stats')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(main()).queryByText('Stats')).not.toBeInTheDocument()
  })

  it('opens everything in a sheet from the phone bar', () => {
    sidebar('/problems')
    const bar = screen.getByRole('navigation', { name: 'Main pages' })
    expect(within(bar).getAllByRole('link').map((a) => a.textContent)).toEqual(['Floor plan', 'Problems', 'Incidents'])
    fireEvent.click(within(bar).getByRole('button', { name: 'Menu' }))
    const sheet = screen.getByRole('dialog', { name: 'Menu' })
    expect(within(sheet).getByRole('button', { name: 'Network' })).toBeInTheDocument()
    fireEvent.click(within(sheet).getByRole('button', { name: 'Close the menu' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers language, theme and sign-out in the account menu', () => {
    sidebar()
    fireEvent.click(within(main()).getByRole('button', { name: 'Signed in as kim' }))
    expect(screen.getByRole('menuitemradio', { name: 'Deutsch' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Sign out' }).closest('form')).toHaveAttribute('action', '/logout')
  })
})
