import { Loader, Stack, Text } from '@mantine/core'
import { Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useDashboard } from '@/api/queries'
import type { DashboardLayout, Tile, WidgetTile } from '@/api/types'
import { TileGrid, WidgetCard } from '../Dashboard'
import { PAGE_URL, type Pane } from './model'
import { PlanPane } from './PlanPane'
import { VIEWS, VIEW_COMPONENTS } from '@/widgets/views'
import { Markdown } from '@/components/Markdown'

const tileKey = (tile: Tile) => `${tile.plugin}/${tile.kind === 'action' ? 'a' : 'w'}/${tile.id}`

function Note({ children }: { children: React.ReactNode }) {
  return <Text c="dimmed" className="fb-pane-note">{children}</Text>
}

function Framed({ title, hide, className = '', children }: { title?: string; hide?: boolean; className?: string; children: React.ReactNode }) {
  return (
    <div className={`fb-pane ${className}`} role={title ? 'region' : undefined} aria-label={title || undefined}>
      {title && !hide && <div className="fb-pane-head"><Text fw={800} className="fb-pane-title" truncate>{title}</Text></div>}
      <div className={`fb-pane-body fb-pane-scroll${hide ? ' fb-pane-headless' : ''}`}>{children}</div>
    </div>
  )
}

function TilePane({ pane }: { pane: Extract<Pane, { kind: 'tile' }> }) {
  const { t } = useTranslation()
  const { data, isPending } = useDashboard()
  const tile = data?.tiles.find((x) => tileKey(x) === pane.tile)
  return (
    <Framed title={pane.title} hide={pane.hide_title}>
      {isPending ? <Loader size="sm" aria-label={t('common.loading')} />
        : tile && tile.kind !== 'action' ? <WidgetCard tile={tile as WidgetTile} /> : <Note>{t('dashboards.pane.tileGone')}</Note>}
    </Framed>
  )
}

function DashboardPane({ pane }: { pane: Extract<Pane, { kind: 'dashboard' }> }) {
  const { t } = useTranslation()
  const tiles = useDashboard()
  const layouts = useQuery({ queryKey: qk.dashboardLayouts, queryFn: () => get<{ layouts: DashboardLayout[] }>('/api/dashboard/layouts') })
  const layout = layouts.data?.layouts.find((l) => l.id === pane.layout)
  const shown = layout ? layout.tiles.map((k) => tiles.data?.tiles.find((x) => tileKey(x) === k)).filter((x): x is Tile => !!x) : []
  return (
    <Framed title={pane.title ?? layout?.name} hide={pane.hide_title}>
      {tiles.isPending || layouts.isPending ? <Loader size="sm" aria-label={t('common.loading')} />
        : !layout ? <Note>{t('dashboards.pane.dashboardGone')}</Note>
        : <TileGrid tiles={shown} columns={layout.columns} />}
    </Framed>
  )
}

function PagePane({ pane }: { pane: Extract<Pane, { kind: 'page' }> }) {
  const { t } = useTranslation()
  const title = pane.title ?? t(`dashboards.page.${pane.page}`)
  return (
    <div className="fb-pane">
      {/* Same site, so the page brings its own sign-in and live updates. */}
      <iframe className="fb-pane-frame" src={PAGE_URL[pane.page]} title={title} />
    </div>
  )
}

function ViewPane({ pane }: { pane: Extract<Pane, { kind: 'view' }> }) {
  const { t } = useTranslation()
  const def = VIEWS.find((v) => v.id === pane.view)
  const View = def ? VIEW_COMPONENTS[def.id] : null
  return (
    <Framed title={pane.title ?? (def ? t(def.label) : undefined)} hide={pane.hide_title}>
      {View ? <Suspense fallback={<Loader size="sm" aria-label={t('common.loading')} />}><View expanded /></Suspense>
        : <Note>{t('dashboards.pane.viewGone')}</Note>}
    </Framed>
  )
}

/** Your own words, big enough to read from across the hall. */
function TextPane({ pane }: { pane: Extract<Pane, { kind: 'text' }> }) {
  const { t } = useTranslation()
  return (
    <Framed title={pane.title} hide={pane.hide_title} className={`fb-pane-text fb-text-${pane.size} fb-text-${pane.align}`}>
      {pane.text ? <Markdown source={pane.text} breaks /> : <Note>{t('dashboards.pane.noText')}</Note>}
    </Framed>
  )
}

/** One pane of a dashboard, whatever it holds. */
export function PaneView({ pane, cycle }: { pane: Pane; cycle?: number }) {
  const { t } = useTranslation()
  switch (pane.kind) {
    case 'plan': return <PlanPane pane={pane} cycle={cycle} />
    case 'tile': return <TilePane pane={pane} />
    case 'dashboard': return <DashboardPane pane={pane} />
    case 'page': return <PagePane pane={pane} />
    case 'view': return <ViewPane pane={pane} />
    case 'text': return <TextPane pane={pane} />
    default: return <Framed title={pane.title} hide={pane.hide_title}><Stack h="100%" justify="center" align="center"><Note>{t('dashboards.pane.empty')}</Note></Stack></Framed>
  }
}
