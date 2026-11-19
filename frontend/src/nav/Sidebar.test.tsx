import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@/i18n'
import type { NavBoot } from './boot'
import { activeHref, group, isServerPage } from './sections'
import { Sidebar, type LinkProps } from './Sidebar'

const pages = [
  { href: '/', id: 'floorPlan', label: 'Floor plan' },
  { href: '/problems', id: 'problems', label: 'Problems' },
  { href: '/incidents', id: 'incidents', label: 'Incidents' },
  { href: '/widgets', id: 'widgets', label: 'Widgets' },
  { href: '/topology', id: 'topology', label: 'Topology' },
  { href: '/settings', id: 'settings', label: 'Settings' },
  { href: '/settings/agents', id: 'agents', label: 'Local agents' },
  { href: '/brand-new', id: 'brandNew', label: 'Brand new page' },
]
const boot: NavBoot = { pages, brand: { logo: null, name: null }, user: { name: 'Kim', username: 'kim' }, signOut: true, prefs: null }
const link = ({ children, ...rest }: LinkProps) => <a {...rest}>{children}</a>

function sidebar(path = '/problems', extra: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  return render(<Sidebar boot={boot} path={path} renderLink={link} onGoTo={() => {}} {...extra} />)
}
const main = () => screen.getByRole('navigation', { name: 'Main' })

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  document.cookie = 'floorbit_nav=; max-age=0; path=/'
})

describe('sections', () => {
  it('puts plugin pages in their own section, never under "more"', () => {
    const g = group([...pages, { href: '/plugins/gs/overview', id: 'plugin:gs:overview', label: 'Game servers', icon: 'gamepad' }])
    expect(g.sections.map((s) => s.id)).toEqual(['network', 'admin', 'plugins', 'more'])
    expect(g.sections.find((s) => s.id === 'plugins')?.pages.map((p) => p.label)).toEqual(['Game servers'])
  })

  it('pins the everyday pages and folds the rest into sections, a new page into "more"', () => {
    const g = group(pages)
    expect(g.pinned.map((p) => p.id)).toEqual(['floorPlan', 'problems', 'incidents'])
    expect(g.sections.map((s) => [s.id, s.pages.map((p) => p.id)])).toEqual([
      ['network', ['widgets', 'topology']], ['admin', ['settings', 'agents']], ['more', ['brandNew']],
    ])
  })

  it('lights one row: the longest page that holds the path', () => {
    expect(activeHref(pages, '/incidents/qr')).toBe('/incidents')
    expect(activeHref(pages, '/settings/agents')).toBe('/settings/agents')
    expect(activeHref(pages, '/nowhere')).toBeNull()
  })

  it('knows which pages Flask draws', () => {
    expect(isServerPage('/')).toBe(true)
    expect(isServerPage('/kiosk')).toBe(true)
    expect(isServerPage('/settings')).toBe(false)
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

  it('opens the section of the page on screen, and folds it when another opens', () => {
    sidebar('/topology')
    expect(within(main()).getByRole('link', { name: 'Topology' })).toHaveAttribute('aria-current', 'page')
    const network = within(main()).getByRole('button', { name: 'Network' })
    const admin = within(main()).getByRole('button', { name: 'Settings' })
    expect(network).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(admin)
    expect(admin).toHaveAttribute('aria-expanded', 'true')
    expect(network).toHaveAttribute('aria-expanded', 'false')
    expect(within(main()).getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    fireEvent.click(admin)
    expect(admin).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps several sections open when folding is switched off', () => {
    sidebar('/topology')
    fireEvent.click(within(main()).getByRole('button', { name: 'Signed in as kim' }))
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Fold other sections when one opens' }))
    expect(JSON.parse(localStorage.getItem('floorbit-nav-prefs')!)).toEqual({ favourites: [], accordion: false })
    const admin = within(main()).getByRole('button', { name: 'Settings' })
    fireEvent.click(admin)
    expect(admin).toHaveAttribute('aria-expanded', 'true')
    expect(within(main()).getByRole('button', { name: 'Network' })).toHaveAttribute('aria-expanded', 'true')
    expect(JSON.parse(localStorage.getItem('floorbit-nav-open')!)).toEqual(['admin'])
  })

  it('pins favourites to the top, saved with the account when signed in', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, prefs: { favourites: ['widgets'], accordion: true } }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    const favs = within(main()).getByRole('list', { name: 'Favourites' })
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Widgets'])
    fireEvent.click(within(main()).getByRole('button', { name: 'Add Incidents to favourites' }))
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Widgets', 'Incidents'])
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me/nav', expect.objectContaining({
      method: 'PUT', body: JSON.stringify({ favourites: ['widgets', 'incidents'], accordion: true }),
    }))
    fireEvent.click(within(favs).getByRole('button', { name: 'Remove Widgets from favourites' }))
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Incidents'])
    expect(localStorage.getItem('floorbit-nav-prefs')).toBeNull()
  })

  it('folds to icons, keeps that in a cookie, and lists a section in a flyout', () => {
    sidebar('/problems')
    fireEvent.click(within(main()).getByRole('button', { name: 'Collapse the sidebar' }))
    expect(main()).toHaveAttribute('data-state', 'rail')
    expect(document.cookie).toContain('floorbit_nav=rail')
    fireEvent.click(within(main()).getByRole('button', { name: 'Network' }))
    expect(within(main()).getByText('Widgets')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(main()).queryByText('Widgets')).not.toBeInTheDocument()
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
    expect(screen.getByRole('menuitemradio', { name: 'Deutsch (Schweiz)' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'Deutsch (Deutschland, Österreich)' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Sign out' }).closest('form')).toHaveAttribute('action', '/logout')
  })

  it('switches to another tenant of someone on a platform with several tenants', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        here: 'club-a', tenants: [
          { id: 'club-b', name: 'Club B', url: 'https://b.example.com', how: 'account' },
          { id: 'club-c', name: 'Club C', url: 'https://c.example.com', how: 'platform' },
        ],
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ url: 'https://b.example.com/switch/arrive?ticket=abc' })))
    vi.stubGlobal('fetch', fetchMock)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    render(<Sidebar boot={{ ...boot, tenants: true }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    fireEvent.click(await within(main()).findByRole('button', { name: /This tenant/ }))
    expect(screen.getByRole('menuitem', { name: /Club C.*as platform admin/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /Club B/ }))
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('https://b.example.com/switch/arrive?ticket=abc'))
    expect(fetchMock).toHaveBeenCalledWith('/api/tenant/mine', expect.anything())
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({ tenant: 'club-b' })
  })

  it('shows no switcher when there is no other tenant to go to', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ here: 'club-a', tenants: [] })))
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, tenants: true }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(within(main()).queryByRole('button', { name: /This tenant/ })).not.toBeInTheDocument()
  })

  it('tells a platform admin visiting that they are one, and offers no switching on', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, tenants: true, user: { name: 'Kim', username: 'platform:kim', platform: true } }}
      path="/problems" renderLink={link} onGoTo={() => {}} />)
    fireEvent.click(within(main()).getByRole('button', { name: 'Signed in as platform:kim' }))
    expect(screen.getByText('Visiting as platform admin')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asks for other tenants only on a platform with several tenants', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    sidebar()
    expect(within(main()).queryByRole('button', { name: /This tenant/ })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('skip link', () => {
  it('moves keyboard focus past the sidebar into the page', () => {
    const page = document.createElement('main')
    page.innerHTML = '<button>First thing on the page</button>'
    document.body.appendChild(page)
    try {
      sidebar()
      fireEvent.click(screen.getByRole('link', { name: 'Skip to content' }))
      expect(document.activeElement).toBe(page)
      expect(page).toHaveAttribute('tabindex', '-1')
    } finally {
      page.remove()
    }
  })

  it('shows the sections admins made, opens the one with the page on screen, and opens addresses in a new tab', () => {
    const custom = [{
      id: 'main-hall', name: 'Main hall', icon: 'star', links: [
        { kind: 'dashboard' as const, href: '/dashboards/wall', label: 'Hall wall' },
        { kind: 'page' as const, href: '/widgets', page: 'widgets', label: 'Widgets', own: false },
        { kind: 'url' as const, href: 'https://example.com/grafana', label: 'Grafana', external: true },
      ],
    }]
    render(<Sidebar boot={{ ...boot, custom }} path="/dashboards/wall" renderLink={link} onGoTo={() => {}} />)
    const head = within(main()).getByRole('button', { name: 'Main hall' })
    expect(head).toHaveAttribute('aria-expanded', 'true')
    expect(within(main()).getByRole('link', { name: 'Hall wall' })).toHaveAttribute('aria-current', 'page')
    const out = within(main()).getByRole('link', { name: 'Grafana' })
    expect(out).toHaveAttribute('target', '_blank')
    expect(out).toHaveAttribute('rel', 'noopener noreferrer')
    // The page link keeps its built-in section too.
    expect(within(main()).getByRole('button', { name: 'Network' })).toHaveAttribute('aria-expanded', 'false')
  })
})
