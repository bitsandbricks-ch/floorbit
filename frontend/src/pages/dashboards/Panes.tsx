import { ActionIcon, Anchor, Loader, Stack, Text, Tooltip } from '@mantine/core'
import { IconArrowsMaximize } from '@tabler/icons-react'
import { useContext, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useDashboard, useWidgets } from '@/api/queries'
import type { Tile, Widget, WidgetTile } from '@/api/types'
import { FitWidget } from '@bitsandbricks/widgets'
import { usePaneData } from '@/widgets/usePaneData'
import { type Pane, displayOf, paneRange, rangedUrl } from './model'
import { PlanPane } from './PlanPane'
import { Markdown } from '@/components/Markdown'
import { publicUrl, useScreen } from './screen'
import { followed } from '../widgets/saved'
import { LargeContext, useMakeLarge } from './large'
import './Panes.css'

const tileKey = (tile: Tile) => `${tile.plugin}/${tile.kind === 'action' ? 'a' : 'w'}/${tile.id}`

function Note({ children }: { children: React.ReactNode }) {
  return <Text c="dimmed" className="fb-pane-note">{children}</Text>
}

/** ``fit``: the body never scrolls; what it holds sizes itself to the box (widgets, issue #924). */
function Framed({ title, hide, className = '', actions, fit, alert, children }: {
  title?: string; hide?: boolean; className?: string; actions?: React.ReactNode; fit?: boolean; alert?: boolean; children: React.ReactNode
}) {
  return (
    <div className={`fb-pane ${className}${alert ? ' fb-pane-alert' : ''}${!title || hide ? ' fb-pane-nohead' : ''}`} role={title ? 'region' : undefined} aria-label={title || undefined}>
      {title && !hide && <div className="fb-pane-head"><Text fw={600} className="fb-pane-title" truncate>{title}</Text>{actions && <div className="bnb-pane-actions">{actions}</div>}</div>}
      <div className={`fb-pane-body ${fit ? 'bnb-pane-fit' : 'fb-pane-scroll'}${hide ? ' fb-pane-headless' : ''}`}>{children}</div>
    </div>
  )
}

/** A tile on a public dashboard read signed out: from the dashboard's own feed. */
function PublicTilePane({ pane, id }: { pane: Extract<Pane, { kind: 'tile' }>; id: string }) {
  const { tiles } = useScreen()
  const sources = [pane.tile, ...(pane.also ?? [])].map((key): WidgetTile => {
    const [plugin, , name] = key.split('/')
    return { plugin, plugin_name: 'Floorbit', id: name, label: tiles[key] ?? name, size: 'small', refresh: 15,
      url: publicUrl(id, `/tiles/${encodeURIComponent(name)}`) }
  })
  return <TileWidgetPane pane={pane} tiles={sources} />
}

function TilePane({ pane }: { pane: Extract<Pane, { kind: 'tile' }> }) {
  const { publicId } = useScreen()
  return publicId ? <PublicTilePane pane={pane} id={publicId} /> : <SignedInTilePane pane={pane} />
}

function SignedInTilePane({ pane }: { pane: Extract<Pane, { kind: 'tile' }> }) {
  const { t } = useTranslation()
  const { data, isPending } = useDashboard()
  const find = (key: string) => data?.tiles.find((x) => tileKey(x) === key && x.kind !== 'action') as WidgetTile | undefined
  const { range: boardRange } = useScreen()
  const timed = paneRange(pane, boardRange)
  const found = find(pane.tile)
  const tile = found && { ...found, url: rangedUrl(found, timed) }
  // A gone extra source just drops out; the pane is gone only when its first tile is.
  const more = (pane.also ?? []).map(find).filter((x): x is WidgetTile => !!x).map((x) => ({ ...x, url: rangedUrl(x, timed) }))
  if (tile) return <TileWidgetPane pane={pane} tiles={[tile, ...more]} />
  return (
    <Framed title={pane.title} hide={pane.hide_title}>
      {isPending ? <Loader size="sm" aria-label={t('common.loading')} /> : <Note>{tileGone(t, pane.tile)}</Note>}
    </Framed>
  )
}

/** Why a tile isn't there. A plugin's tile (``<plugin>/w/<id>``), often on a dashboard brought from
 *  another Floorbit (#938), says which plugin it needs. */
function tileGone(t: (k: string, o?: Record<string, string>) => string, tile: string): string {
  const plugin = tile.split('/w/')[0]
  return plugin && plugin !== 'floorbit' ? t('dashboards.pane.tileNeeds', { plugin }) : t('dashboards.pane.tileGone')
}

/** The names a status or list widget shows as down. */
function listsDown(widget: Widget): string[] {
  if (widget.type === 'status') return widget.items.filter((x) => x.state === 'down').map((x) => x.label)
  if (widget.type === 'list') return widget.items.filter((x) => x.tone === 'err').map((x) => x.label)
  return []
}

/** A data widget in its pane: it fits the box at the level the box allows. "+N more" and the
 *  button open it large in the dashboard's area (#925); Esc goes back. */
function TileWidgetPane({ pane, tiles }: { pane: Extract<Pane, { kind: 'tile' }>; tiles: WidgetTile[] }) {
  const { t } = useTranslation()
  const large = useContext(LargeContext)
  const makeLarge = useMakeLarge()
  const paced = pane.refresh ? tiles.map((x) => ({ ...x, refresh: pane.refresh! })) : tiles
  const { data, error, isPending, dropped } = usePaneData(useWidgets(paced), pane, tiles.map((x) => x.label), displayOf(pane))
  const title = pane.title ?? tiles.map((x) => x.label).join(' · ')
  const look = { stack: pane.stack, style: pane.style, trend: pane.trend, legend: pane.legend,
    thresholds: pane.threshold_mode === 'percent' ? undefined : pane.thresholds, number: { decimals: pane.decimals, short: pane.short },
    axis: { min: pane.y_min, max: pane.y_max, log: pane.y_log }, spark: pane.spark, change: pane.change, text: pane.text_size }
  const link = data?.link && data.link.startsWith('/') ? data.link : ''
  const { alerts, pulsing } = useScreen()
  // A wall's eye goes to the pane that lists what just went down and nobody has taken (#1137).
  const alert = !!alerts?.length && !!data && listsDown(data).some((name) => alerts.includes(name))
  useEffect(() => {
    if (!alert || !pulsing) return undefined
    pulsing(true)
    return () => pulsing(false)
  }, [alert, pulsing])
  return (
    <Framed title={title} hide={pane.hide_title} fit alert={alert} actions={data && (
      <>
        {/* One quiet "Open" on tiles that lead somewhere; the big view's button only on hover or
            focus, so a row of tiles doesn't carry an icon pair each (#1407). */}
        {link && (
          <Anchor href={link} size="xs" c="dimmed" className="fb-pane-open" aria-label={t('widgets.kind.detailsNamed', { name: title })}>
            {t('widgets.kind.open')}
          </Anchor>
        )}
        {makeLarge && (
          <Tooltip label={t('dashboards.pane.openBig')}>
            <ActionIcon variant="subtle" color="gray" size="sm" className="fb-pane-hover" aria-label={t('dashboards.pane.openBigNamed', { name: title })} onClick={makeLarge}>
              <IconArrowsMaximize size={15} />
            </ActionIcon>
          </Tooltip>
        )}
      </>
    )}>
      {isPending ? <Loader size="sm" aria-label={t('common.loading')} />
        : error && !data ? <Text size="sm" className="fb-tone-err fb-pane-note" role="alert">✕ {error.message}</Text>
          : data ? <FitWidget widget={data} pick={pane.type} pin={large ? 'l' : pane.level} look={look} onMore={makeLarge ?? undefined} /> : null}
      {dropped.length > 0 && <Text size="xs" c="dimmed" className="fb-pane-note">{t('dashboards.pane.dropped', { names: dropped.join(', ') })}</Text>}
    </Framed>
  )
}

/** A saved widget: drawn as its tile pane, so a change on the Widgets page shows here too. */
function WidgetPane({ pane }: { pane: Extract<Pane, { kind: 'widget' }> }) {
  const { t } = useTranslation()
  if (pane.saved) return <TilePane pane={followed(pane.saved, pane)} />
  return <Framed title={pane.title} hide={pane.hide_title}><Note>{t('dashboards.pane.widgetGone')}</Note></Framed>
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
    case 'widget': return <WidgetPane pane={pane} />
    case 'text': return <TextPane pane={pane} />
    case 'private': return <Framed title={pane.title} hide={pane.hide_title}><Stack h="100%" justify="center" align="center"><Note>{t('dashboards.pane.private')}</Note></Stack></Framed>
    default: return <Framed title={pane.title} hide={pane.hide_title}><Stack h="100%" justify="center" align="center"><Note>{t('dashboards.pane.empty')}</Note></Stack></Framed>
  }
}
