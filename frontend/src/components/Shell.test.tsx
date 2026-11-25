import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { crumbsFor } from '@/nav/crumbs'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Layout } from './Layout'
import { PageTabs } from '@bitsandbricks/ui'
import { usePageTab } from './pageTab'
import { TopBarCrumbs, TopBarEnd } from './TopBar'
import type { NavPage } from '@/nav/sections'

const TopBar = ({ pages }: { pages: NavPage[] }) => <><TopBarCrumbs pages={pages} /><TopBarEnd phone={false} /></>

afterEach(() => vi.unstubAllGlobals())

const pages = [
  { href: '/overview', id: 'overview', label: 'Overview' },
  { href: '/firewalls', id: 'firewalls', label: 'Firewalls' },
  { href: '/settings/agents', id: 'agents', label: 'Local agents' },
  { href: '/plugins/gs/overview', id: 'plugin:gs:overview', label: 'Game servers' },
]
const problems = {
  problems: [
    { id: 'a', kind: 'switch', level: 'warn', title: 'Uplink at 1G', where: 'sw-c-02', since: 1, link: '/problems' },
    { id: 'b', kind: 'switch', level: 'down', title: 'fw-07 down', where: 'Hall 2', since: 2, link: '/plan?view=topology' },
  ],
  counts: { down: 1, warn: 1, muted: 0 }, mutes: [], quiet_hours: false, checked_at: 3, can_mute: false,
}

describe('breadcrumbs', () => {
  it('names the group and the page, and plugins under Plugins', () => {
    // Firewalls is a tab of the Network row.
    expect(crumbsFor(pages, '/firewalls')).toMatchObject({ section: 'monitoring', page: { id: 'network', href: '/firewalls' } })
    expect(crumbsFor(pages, '/settings/agents/rack-a')).toEqual({ section: 'monitoring', page: pages[2] })
    expect(crumbsFor(pages, '/plugins/gs/overview').section).toBe('plugins')
    expect(crumbsFor(pages, '/nowhere')).toEqual({ section: null, page: null })
  })

  it('puts a Settings tab under Settings, also for an account that only has the tab', () => {
    const settings = { href: '/settings', id: 'settings', label: 'Settings' }
    const users = { href: '/settings/users', id: 'users', label: 'Users' }
    // Settings sits at the foot of the sidebar, in no group.
    expect(crumbsFor([settings, users], '/settings/users')).toMatchObject({ section: null, page: settings })
    expect(crumbsFor([users], '/settings/users')).toMatchObject({ section: null, page: { href: '/settings/users', id: 'settings' } })
  })
})

describe('top bar', () => {
  it('shows where you are, a sub page under its page, and the problems behind the bell', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/problems': problems }).fn)
    renderWithApp(<><TopBar pages={pages} /><Layout title="Rack A"><p>agent</p></Layout></>, '/settings/agents/rack-a')
    const crumbs = screen.getByRole('navigation', { name: 'Where you are' })
    expect(crumbs).toHaveTextContent('Monitoring')
    expect(within(crumbs).getByRole('link', { name: 'Local agents' })).toHaveAttribute('href', '/settings/agents')
    expect(within(crumbs).getByText('Rack A')).toHaveAttribute('aria-current', 'page')
    fireEvent.click(await screen.findByRole('button', { name: 'Notifications (2)' }))
    const list = await screen.findByRole('list', { name: 'Notifications' })
    const rows = within(list).getAllByRole('button')
    // What is down comes first.
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining('fw-07 down'), expect.stringContaining('Uplink at 1G')])
  })

  it('says a section once when its page has the same name', () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/problems': problems }).fn)
    // A plugin's page called "Plugins" sits in the Plugins section.
    const own = { href: '/plugins/kit/home', id: 'plugin:kit:home', label: 'Plugins' }
    renderWithApp(<><TopBar pages={[own]} /><Layout title="core-01"><p>device</p></Layout></>, '/plugins/kit/home/d1')
    const crumbs = screen.getByRole('navigation', { name: 'Where you are' })
    expect(crumbs).toHaveTextContent(/^Pluginscore-01$/)
  })
})

function Tabs() {
  const [tab, setTab] = usePageTab(['agents', 'failover'])
  return (
    <>
      <PageTabs label="Agents" active={tab} onChange={setTab}
        tabs={[{ id: 'agents', label: 'Agents', count: 3 }, { id: 'failover', label: 'Failover', alert: 'warn' }]} />
      <p>on {tab}</p>
    </>
  )
}

describe('page tabs', () => {
  it('keeps the tab in the address, with counts and arrow keys', () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<Tabs />, '/settings/agents?tab=failover')
    expect(screen.getByRole('tab', { name: /Failover/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Agents/ })).toHaveTextContent('3')
    fireEvent.keyDown(screen.getByRole('tab', { name: /Failover/ }), { key: 'ArrowRight' })
    expect(screen.getByText('on agents')).toBeInTheDocument()
  })
})

describe('notifications panel', () => {
  it('shows the picked notification beside the list and leads to its problem page', async () => {
    const detail = { problem: problems.problems[1], device: null, can_mute: false, can_report: false, may_see_people: false }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/problems': problems, 'GET /api/problems/b': detail }).fn)
    renderWithApp(<TopBar pages={pages} />, '/overview')
    fireEvent.click(await screen.findByRole('button', { name: 'Notifications (2)' }))
    // The worst one is picked at first, so the details are never empty.
    expect(await screen.findByRole('link', { name: 'Open problem' })).toHaveAttribute('href', '/problems/b')
    const list = screen.getByRole('list', { name: 'Notifications' })
    fireEvent.click(within(list).getByRole('button', { name: /Uplink at 1G/ }))
    expect(within(list).getByRole('button', { name: /Uplink at 1G/ })).toHaveAttribute('aria-current', 'true')
  })
})
