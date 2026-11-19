import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@/i18n'
import { resetNavPrefs, type NavBoot } from './boot'
import { activeHref, group, hubTabs, isServerPage } from './sections'
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
  resetNavPrefs()
  vi.unstubAllGlobals()
  localStorage.clear()
  document.cookie = 'floorbit_nav=; max-age=0; path=/'
})

describe('sections', () => {
  it('puts plugin pages in their own section, never under "more"', () => {
    const g = group([...pages, { href: '/plugins/gs/overview', id: 'plugin:gs:overview', label: 'Game servers', icon: 'gamepad' }])
    expect(g.sections.map((s) => s.id)).toEqual(['work', 'monitoring', 'screens', 'plugins', 'more'])
    expect(g.sections.find((s) => s.id === 'plugins')?.pages.map((p) => p.label)).toEqual(['Game servers'])
  })

  it('pins the start pages and sorts the rest into a few rows, a new page into "more"', () => {
    const g = group(pages)
    expect(g.pinned.map((p) => p.id)).toEqual(['floorPlan'])
    // Problems and Incidents are Helpdesk's tabs, Topology is Network's, Widgets Dashboards'; Settings sits at the foot.
    expect(g.sections.map((s) => [s.id, s.pages.map((p) => p.id)])).toEqual([
      ['work', ['helpdesk']], ['monitoring', ['network', 'agents']], ['screens', ['dashboards']], ['more', ['brandNew']],
    ])
    const helpdesk = g.sections[0].pages[0]
    expect(helpdesk).toMatchObject({ href: '/problems', also: ['/incidents'] })
  })

  it("lists a row's tabs this account may open, the row's own page first", () => {
    expect(hubTabs(pages, '/incidents/qr')?.tabs.map((p) => p.id)).toEqual(['problems', 'incidents'])
    expect(hubTabs(pages, '/topology')).toBeNull()   // one tab only: no strip
    expect(hubTabs(pages, '/settings/users')).toBeNull()   // Settings draws its own tabs
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
  it('shows the Settings tabs (Users) as the Settings row, lit while one is on screen', () => {
    const withUsers = [...pages, { href: '/settings/users', id: 'users', label: 'Users' }]
    render(<Sidebar boot={{ ...boot, pages: withUsers }} path="/settings/users" renderLink={link} onGoTo={() => {}} />)
    expect(within(main()).queryByRole('link', { name: 'Users' })).toBeNull()
    expect(within(main()).getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page')
  })

  it('names Plugins and Settings at the foot, not just a gear icon', () => {
    const withPlugins = [...pages, { href: '/settings/plugins', id: 'plugins', label: 'Plugins' }]
    render(<Sidebar boot={{ ...boot, pages: withPlugins }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    const admin = within(main()).getByRole('list', { name: 'Plugins and settings' })
    expect(within(admin).getByRole('link', { name: 'Plugins' })).toHaveAttribute('href', '/settings/plugins')
    expect(within(admin).getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings')
  })

  it('marks the page on screen and shows how many switches are down', () => {
    sidebar('/incidents', { down: 3 })
    const row = within(main()).getByRole('link', { name: /Helpdesk/ })
    expect(row).toHaveAttribute('aria-current', 'page')
    expect(row).toHaveTextContent('3 down')
  })

  it('shows every group open, folds one on a click, and remembers it on this browser', () => {
    sidebar('/topology')
    expect(within(main()).getByRole('link', { name: 'Network' })).toHaveAttribute('aria-current', 'page')
    const live = within(main()).getByRole('button', { name: 'Work' })
    expect(live).toHaveAttribute('aria-expanded', 'true')
    expect(within(main()).getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    fireEvent.click(live)
    expect(live).toHaveAttribute('aria-expanded', 'false')
    expect(within(main()).queryByRole('link', { name: /Helpdesk/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('floorbit-nav-folded')!)).toContain('work')
    // The group with the page on screen stays open.
    const monitoring = within(main()).getByRole('button', { name: 'Monitoring' })
    fireEvent.click(monitoring)
    expect(monitoring).toHaveAttribute('aria-expanded', 'true')
  })

  it("keeps the event's pages out of the groups: they are in the event menu", () => {
    render(<Sidebar boot={{ ...boot, pages: [...pages, { href: '/replay', id: 'replay', label: 'Event replay' }] }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    expect(within(main()).queryByRole('link', { name: 'Event replay' })).not.toBeInTheDocument()
    expect(within(main()).queryByRole('button', { name: 'Event' })).not.toBeInTheDocument()
  })

  it('pins favourites to the top, saved with the account when signed in', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, prefs: { favourites: ['widgets'], accordion: true } }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    const favs = within(main()).getByRole('list', { name: 'Favourites' })
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Widgets'])
    fireEvent.click(within(main()).getByRole('button', { name: 'Add Helpdesk to favourites' }))
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Widgets', 'Helpdesk'])
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me/nav', expect.objectContaining({
      method: 'PUT', body: JSON.stringify({ favourites: ['widgets', 'helpdesk'], accordion: true }),
    }))
    fireEvent.click(within(favs).getByRole('button', { name: 'Remove Widgets from favourites' }))
    expect(within(favs).getAllByRole('link').map((a) => a.textContent)).toEqual(['Helpdesk'])
    expect(localStorage.getItem('floorbit-nav-prefs')).toBeNull()
  })

  it('lists pinned dashboards with the favourites, lit while one is on screen', () => {
    render(<Sidebar boot={{ ...boot, prefs: { favourites: ['dashboard:hall-b'], accordion: true } }} path="/dashboards/view/hall-b"
      renderLink={link} onGoTo={() => {}} dashboards={[{ id: 'hall-b', name: 'Hall B' }, { id: 'ops', name: 'Ops desk' }]} />)
    const favs = within(main()).getByRole('list', { name: 'Favourites' })
    const row = within(favs).getByRole('link', { name: 'Hall B' })
    expect(row).toHaveAttribute('href', '/dashboards/view/hall-b')
    expect(row).toHaveAttribute('aria-current', 'page')
    expect(within(main()).queryByRole('link', { name: 'Ops desk' })).not.toBeInTheDocument()
  })

  it('folds to icons, keeps that in a cookie, and shows every page as an icon with its name', () => {
    sidebar('/problems')
    fireEvent.click(within(main()).getByRole('button', { name: 'Collapse the sidebar' }))
    expect(main()).toHaveAttribute('data-state', 'rail')
    expect(document.cookie).toContain('floorbit_nav=rail')
    expect(within(main()).queryByRole('button', { name: 'Work' })).not.toBeInTheDocument()
    expect(within(main()).getByRole('link', { name: 'Dashboards' })).toHaveAttribute('title', 'Dashboards')
  })

  it('opens everything in a sheet from the phone bar', () => {
    sidebar('/problems')
    const bar = screen.getByRole('navigation', { name: 'Main pages' })
    expect(within(bar).getAllByRole('link').map((a) => a.textContent)).toEqual(['Floor plan', 'Helpdesk'])
    fireEvent.click(within(bar).getByRole('button', { name: 'Menu' }))
    const sheet = screen.getByRole('dialog', { name: 'Menu' })
    expect(within(sheet).getByRole('button', { name: 'Monitoring' })).toBeInTheDocument()
    expect(within(sheet).getByRole('button', { name: /Go to/ })).toBeInTheDocument()
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
    const fetchMock = vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(
      url === '/api/tenant/mine'
        ? {
            here: 'club-a', tenants: [
              { id: 'club-b', name: 'Club B', url: 'https://b.example.com', how: 'account' },
              { id: 'club-c', name: 'Club C', url: 'https://c.example.com', how: 'platform' },
            ],
          }
        : url === '/api/tenant/switch' ? { url: 'https://b.example.com/switch/arrive?ticket=abc' } : {},
    ))))
    vi.stubGlobal('fetch', fetchMock)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    render(<Sidebar boot={{ ...boot, tenants: true }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    fireEvent.click(await within(main()).findByRole('button', { name: /This tenant/ }))
    expect(screen.getByRole('menuitem', { name: /Club C.*as platform admin/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /Club B/ }))
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('https://b.example.com/switch/arrive?ticket=abc'))
    expect(fetchMock).toHaveBeenCalledWith('/api/tenant/mine', expect.anything())
    const call = fetchMock.mock.calls.find((c) => c[0] === '/api/tenant/switch') as unknown as [string, RequestInit]
    expect(JSON.parse(call[1].body as string)).toEqual({ tenant: 'club-b' })
  })

  it('shows no switcher when there is no other tenant to go to', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ here: 'club-a', tenants: [] })))
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, tenants: true }} path="/problems" renderLink={link} onGoTo={() => {}} />)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(within(main()).queryByRole('button', { name: /This tenant/ })).not.toBeInTheDocument()
  })

  it('tells a platform admin visiting that they are one, and offers no switching on', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    render(<Sidebar boot={{ ...boot, tenants: true, user: { name: 'Kim', username: 'platform:kim', platform: true } }}
      path="/problems" renderLink={link} onGoTo={() => {}} />)
    fireEvent.click(within(main()).getByRole('button', { name: 'Signed in as platform:kim' }))
    expect(screen.getByText('Visiting as platform admin')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith('/api/tenant/mine', expect.anything())
  })

  it('asks for other tenants only on a platform with several tenants', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    sidebar()
    expect(within(main()).queryByRole('button', { name: /This tenant/ })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith('/api/tenant/mine', expect.anything())
  })

  it('shows the event this browser works on and switches to another', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      live: 'e1', current: 'e1', events: [
        { id: 'e1', name: 'Spring LAN', status: 'live' }, { id: 'e2', name: 'Autumn LAN', status: 'planning' },
      ],
    }))))
    vi.stubGlobal('fetch', fetchMock)
    sidebar()
    const picker = await within(main()).findByRole('button', { name: /Spring LAN/ })
    fireEvent.click(picker)
    expect(screen.getByRole('menuitemradio', { name: /Spring LAN/ })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByRole('menuitemradio', { name: /Autumn LAN/ }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/tenant/current', expect.objectContaining({ body: JSON.stringify({ event: 'e2' }) })))
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
    // The page link keeps its built-in group too.
    expect(within(main()).getByRole('button', { name: 'Work' })).toHaveAttribute('aria-expanded', 'true')
  })
})
