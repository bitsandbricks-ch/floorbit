import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from '@bitsandbricks/ui'
import { fakeFetch, renderWithApp } from '@/test/render'
import { resetNavPrefs, type NavBoot } from './boot'
import { activeHref, group, hubTabs, isServerPage } from './sections'
import { useShellNav, type ShellNavProps } from './ShellNav'

const pages = [
  { href: '/', id: 'floorPlan', label: 'Floor plan' },
  { href: '/problems', id: 'problems', label: 'Problems' },
  { href: '/incidents', id: 'incidents', label: 'Incidents' },
  { href: '/widgets', id: 'widgets', label: 'Widgets' },
  { href: '/firewalls', id: 'firewalls', label: 'Firewalls' },
  { href: '/plan?view=topology', id: 'topology', label: 'Topology' },
  { href: '/settings', id: 'settings', label: 'Settings' },
  { href: '/settings/agents', id: 'agents', label: 'Local agents' },
  { href: '/brand-new', id: 'brandNew', label: 'Brand new page' },
]
const boot: NavBoot = { pages, brand: { logo: null, name: null }, user: { name: 'Kim', username: 'kim' }, signOut: true, prefs: null }

// Mantine's menus close again in jsdom once their transition ends, so the tests read menu items
// with hidden: true, as the package's own tests do.
function Shell(props: ShellNavProps) {
  const s = useShellNav(props)
  return (
    <AppShell brand={s.brand(s.folded)} navTop={s.navTop} nav={s.nav} navFooter={s.navFooter}
      folded={s.folded} onFoldedChange={s.onFoldedChange} phoneNav={s.phoneNav}>
      <p>page</p>
    </AppShell>
  )
}

function sidebar(path = '/problems', extra: Partial<ShellNavProps> = {}) {
  return renderWithApp(<Shell boot={boot} path={path} {...extra} />, path)
}
const main = () => screen.getByRole('navigation', { name: 'Main' })
const aside = () => main().closest('aside') as HTMLElement

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
    expect(hubTabs(pages, '/firewalls')).toBeNull()   // one tab only: no strip
    expect(hubTabs(pages, '/settings/users')).toBeNull()   // Settings draws its own tabs
  })

  it('puts the Monitoring pages under their rows', () => {
    const mon = [
      { href: '/services', id: 'services', label: 'Services' }, { href: '/dns', id: 'dns', label: 'DNS' },
      { href: '/traffic', id: 'traffic', label: 'Traffic' }, { href: '/games', id: 'games', label: 'Games' },
      { href: '/firewalls', id: 'firewalls', label: 'Firewalls' }, { href: '/wifi', id: 'wifi', label: 'Wi-Fi' },
    ]
    expect(hubTabs(mon, '/dns')?.tabs.map((p) => p.id)).toEqual(['services', 'dns'])
    expect(hubTabs(mon, '/games')?.tabs.map((p) => p.id)).toEqual(['traffic', 'games'])
    expect(hubTabs(mon, '/wifi')?.tabs.map((p) => p.id)).toEqual(['firewalls', 'wifi'])
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

describe('the sidebar', () => {
  it('shows the Settings tabs (Users) as the Settings row, lit while one is on screen', () => {
    sidebar('/settings/users', { boot: { ...boot, pages: [...pages, { href: '/settings/users', id: 'users', label: 'Users' }] } })
    expect(within(main()).queryByRole('link', { name: 'Users' })).toBeNull()
    expect(within(main()).getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page')
  })

  it('names Plugins and Settings at the foot, and lights Plugins on the plugin pages', () => {
    const withPlugins = [...pages, { href: '/settings/plugins', id: 'plugins', label: 'Plugins' }]
    sidebar('/settings/plugins/netbox', { boot: { ...boot, pages: withPlugins } })
    const links = within(main()).getAllByRole('link').map((a) => a.textContent)
    expect(links.slice(-2)).toEqual(['Plugins', 'Settings'])
    expect(within(main()).getByRole('link', { name: 'Plugins' })).toHaveAttribute('aria-current', 'page')
    expect(within(main()).getByRole('link', { name: 'Settings' })).not.toHaveAttribute('aria-current')
  })

  it('marks the page on screen and shows how many switches are down', () => {
    sidebar('/incidents', { down: 3 })
    const row = within(main()).getByRole('link', { name: /Helpdesk/ })
    expect(row).toHaveAttribute('aria-current', 'page')
    expect(row).toHaveTextContent('3 down')
  })

  it('shows every group open, folds one on a click, and remembers it on this browser', () => {
    sidebar('/firewalls')
    expect(within(main()).getByRole('link', { name: 'Network' })).toHaveAttribute('aria-current', 'page')
    // The topology is a view of the floor plan (#1330): "Go to" finds it, the sidebar has no row for it.
    expect(within(main()).queryByRole('link', { name: 'Topology' })).not.toBeInTheDocument()
    const work = within(main()).getByRole('button', { name: 'Work' })
    expect(work).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(work)
    expect(work).toHaveAttribute('aria-expanded', 'false')
    expect(within(main()).queryByRole('link', { name: /Helpdesk/ })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('floorbit-nav-folded')!)).toContain('work')
    // The group with the page on screen stays open.
    const monitoring = within(main()).getByRole('button', { name: 'Monitoring' })
    fireEvent.click(monitoring)
    expect(monitoring).toHaveAttribute('aria-expanded', 'true')
  })

  it("gives Events a row of its own under the start pages, lit by the event's pages (#1201)", () => {
    const more = [...pages, { href: '/events', id: 'events', label: 'Events' }, { href: '/replay', id: 'replay', label: 'Event replay' }]
    sidebar('/replay', { boot: { ...boot, pages: more } })
    expect(within(main()).queryByRole('link', { name: 'Event replay' })).not.toBeInTheDocument()
    expect(within(main()).getByRole('link', { name: 'Events' })).toHaveAttribute('aria-current', 'page')
  })

  it('pins favourites to the top, saved with the account when signed in', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    sidebar('/problems', { boot: { ...boot, prefs: { favourites: ['widgets'], accordion: true } } })
    const first = () => within(main()).getAllByRole('link').map((a) => a.textContent)
    expect(within(main()).getByText('Favourites')).toBeInTheDocument()
    expect(first()[0]).toBe('Widgets')
    fireEvent.click(within(main()).getByRole('button', { name: 'Add Helpdesk to favourites' }))
    expect(first().slice(0, 2)).toEqual(['Widgets', 'Helpdesk'])
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me/nav', expect.objectContaining({
      method: 'PUT', body: JSON.stringify({ favourites: ['widgets', 'helpdesk'], accordion: true }),
    }))
    fireEvent.click(within(main()).getAllByRole('button', { name: 'Remove Widgets from favourites' })[0])
    expect(first()[0]).toBe('Helpdesk')
    expect(localStorage.getItem('floorbit-nav-prefs')).toBeNull()
  })

  it('lists pinned dashboards with the favourites, lit while one is on screen', () => {
    sidebar('/dashboards/view/hall-b', {
      boot: { ...boot, prefs: { favourites: ['dashboard:hall-b'], accordion: true } },
      dashboards: [{ id: 'hall-b', name: 'Hall B' }, { id: 'ops', name: 'Ops desk' }],
    })
    const row = within(main()).getByRole('link', { name: 'Hall B' })
    expect(row).toHaveAttribute('href', '/dashboards/view/hall-b')
    expect(row).toHaveAttribute('aria-current', 'page')
    expect(within(main()).queryByRole('link', { name: 'Ops desk' })).not.toBeInTheDocument()
  })

  it('folds to icons, keeps that in a cookie, and shows every page as an icon with its name', () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    sidebar('/problems')
    fireEvent.click(screen.getByRole('button', { name: 'Fold the sidebar' }))
    expect(aside()).toHaveClass('is-folded')
    expect(document.cookie).toContain('floorbit_nav=rail')
    expect(within(main()).queryByRole('button', { name: 'Work' })).not.toBeInTheDocument()
    expect(within(main()).getByRole('link', { name: 'Dashboards' })).toHaveAttribute('title', 'Dashboards')
  })

  it('offers language, theme and sign-out in the account menu', async () => {
    sidebar()
    fireEvent.click(await within(aside()).findByRole('button', { name: /Signed in as kim/ }))
    expect(await screen.findByRole('menuitem', { name: 'English', hidden: true })).toHaveAttribute('aria-current', 'true')
    expect(await screen.findByRole('menuitem', { name: 'Deutsch (Schweiz)', hidden: true })).toBeInTheDocument()
    expect(await screen.findByRole('menuitem', { name: 'Deutsch (Deutschland, Österreich)', hidden: true })).toBeInTheDocument()
    expect((await screen.findByRole('menuitem', { name: 'Sign out', hidden: true })).closest('form')).toHaveAttribute('action', '/logout')
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
    sidebar('/problems', { boot: { ...boot, tenants: true } })
    fireEvent.click(await within(aside()).findByRole('button', { name: /This tenant/ }))
    expect(await screen.findByRole('menuitem', { name: /Club C.*as platform admin/, hidden: true })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('menuitem', { name: /Club B/, hidden: true }))
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('https://b.example.com/switch/arrive?ticket=abc'))
    const call = fetchMock.mock.calls.find((c) => c[0] === '/api/tenant/switch') as unknown as [string, RequestInit]
    expect(JSON.parse(call[1].body as string)).toEqual({ tenant: 'club-b' })
  })

  it('shows no switcher when there is no other tenant to go to', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ here: 'club-a', tenants: [] })))
    vi.stubGlobal('fetch', fetchMock)
    sidebar('/problems', { boot: { ...boot, tenants: true } })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/tenant/mine', expect.anything()))
    expect(within(aside()).queryByRole('button', { name: /This tenant/ })).not.toBeInTheDocument()
  })

  it('tells a platform admin visiting that they are one, and offers no switching on', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetchMock)
    sidebar('/problems', { boot: { ...boot, tenants: true, user: { name: 'Kim', username: 'platform:kim', platform: true } } })
    fireEvent.click(await within(aside()).findByRole('button', { name: /Signed in as platform:kim/ }))
    expect(await screen.findByText('Visiting as platform admin')).toBeInTheDocument()
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
    fireEvent.click(await within(aside()).findByRole('button', { name: /Spring LAN/ }))
    expect(await screen.findByRole('menuitem', { name: /Spring LAN/, hidden: true })).toHaveAttribute('aria-current', 'true')
    fireEvent.click(await screen.findByRole('menuitem', { name: /Autumn LAN/, hidden: true }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/tenant/current', expect.objectContaining({ body: JSON.stringify({ event: 'e2' }) })))
  })

  it('shows the sections admins made, opens the one with the page on screen, and opens addresses in a new tab', () => {
    const custom = [{
      id: 'main-hall', name: 'Main hall', icon: 'star', links: [
        { kind: 'dashboard' as const, href: '/dashboards/wall', label: 'Hall wall' },
        { kind: 'page' as const, href: '/widgets', page: 'widgets', label: 'Widgets', own: false },
        { kind: 'url' as const, href: 'https://example.com/grafana', label: 'Grafana', external: true },
      ],
    }]
    sidebar('/dashboards/wall', { boot: { ...boot, custom } })
    expect(within(main()).getByRole('button', { name: 'Main hall' })).toHaveAttribute('aria-expanded', 'true')
    expect(within(main()).getByRole('link', { name: 'Hall wall' })).toHaveAttribute('aria-current', 'page')
    const out = within(main()).getByRole('link', { name: 'Grafana' })
    expect(out).toHaveAttribute('target', '_blank')
    expect(out).toHaveAttribute('rel', 'noopener noreferrer')
    // The page link keeps its built-in group too.
    expect(within(main()).getByRole('button', { name: 'Work' })).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('the phone bar', () => {
  it('shows the main pages and opens every page from "More"', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('max-width'), media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }))
    sidebar('/problems')
    const bar = screen.getByRole('navigation', { name: 'Pages' })
    expect(within(bar).getAllByRole('link').map((a) => a.textContent)).toEqual(['Floor plan', 'Helpdesk'])
    fireEvent.click(within(bar).getByRole('button', { name: 'More' }))
    const sheet = await screen.findByRole('dialog', { name: 'Every page' })
    expect(within(sheet).getByRole('button', { name: 'Monitoring' })).toBeInTheDocument()
    expect(within(sheet).getByRole('link', { name: 'Settings' })).toBeInTheDocument()
  })
})

describe('Set up at the foot (#1437)', () => {
  const withSetup = [...pages, { href: '/setup', id: 'setup', label: 'Set up' }]
  it('shows Set up with its progress next to Settings while steps are open, and not in the groups', () => {
    renderWithApp(<Shell boot={{ ...boot, pages: withSetup }} path="/problems" setup={{ done: 4, count: 7 }} />, '/problems')
    const link = within(main()).getByRole('link', { name: /Set up/ })
    expect(link).toHaveAttribute('href', '/setup')
    expect(within(link).getByText('4/7')).toBeInTheDocument()
    expect(within(main()).getAllByRole('link', { name: /Set up/ })).toHaveLength(1)
    // At the foot with Plugins and Settings, not among the groups.
    const names = within(main()).getAllByRole('link').map((a) => a.textContent)
    expect(names.indexOf('Settings')).toBeGreaterThan(names.indexOf('Set up4/7'))
  })
  it('leaves it out once every step is done', () => {
    renderWithApp(<Shell boot={{ ...boot, pages: withSetup }} path="/problems" setup={{ done: 7, count: 7 }} />, '/problems')
    expect(within(main()).queryByRole('link', { name: /Set up/ })).not.toBeInTheDocument()
  })
})
