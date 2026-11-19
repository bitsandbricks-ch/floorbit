import { ActionIcon, Loader, Modal, Stack, Text, Tooltip } from '@mantine/core'
import { IconArrowsMaximize, IconExternalLink } from '@tabler/icons-react'
import { Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDashboard, useFeaturesOff, useWidget } from '@/api/queries'
import type { Tile, WidgetTile } from '@/api/types'
import { FitWidget } from '@/widgets/FitWidget'
import type { Pane } from './model'
import { PlanPane } from './PlanPane'
import { VIEWS, VIEW_COMPONENTS } from '@/widgets/views'
import { Markdown } from '@/components/Markdown'
import { publicUrl, useScreen } from './screen'

const tileKey = (tile: Tile) => `${tile.plugin}/${tile.kind === 'action' ? 'a' : 'w'}/${tile.id}`

function Note({ children }: { children: React.ReactNode }) {
  return <Text c="dimmed" className="fb-pane-note">{children}</Text>
}

/** ``fit``: the body never scrolls; what it holds sizes itself to the box (widgets, issue #924). */
function Framed({ title, hide, className = '', actions, fit, children }: {
  title?: string; hide?: boolean; className?: string; actions?: React.ReactNode; fit?: boolean; children: React.ReactNode
}) {
  return (
    <div className={`fb-pane ${className}${!title || hide ? ' fb-pane-nohead' : ''}`} role={title ? 'region' : undefined} aria-label={title || undefined}>
      {title && !hide && <div className="fb-pane-head"><Text fw={800} className="fb-pane-title" truncate>{title}</Text>{actions && <div className="fb-pane-actions">{actions}</div>}</div>}
      <div className={`fb-pane-body ${fit ? 'fb-pane-fit' : 'fb-pane-scroll'}${hide ? ' fb-pane-headless' : ''}`}>{children}</div>
    </div>
  )
}

/** A tile on a public dashboard read signed out: from the dashboard's own feed. */
function PublicTilePane({ pane, id }: { pane: Extract<Pane, { kind: 'tile' }>; id: string }) {
  const { tiles } = useScreen()
  const [plugin, , name] = pane.tile.split('/')
  const tile: WidgetTile = {
    plugin, plugin_name: 'Floorbit', id: name, label: tiles[pane.tile] ?? name, size: 'small', refresh: 15,
    url: publicUrl(id, `/tiles/${encodeURIComponent(name)}`),
  }
  return <TileWidgetPane pane={pane} tile={tile} />
}

function TilePane({ pane }: { pane: Extract<Pane, { kind: 'tile' }> }) {
  const { publicId } = useScreen()
  return publicId ? <PublicTilePane pane={pane} id={publicId} /> : <SignedInTilePane pane={pane} />
}

function SignedInTilePane({ pane }: { pane: Extract<Pane, { kind: 'tile' }> }) {
  const { t } = useTranslation()
  const { data, isPending } = useDashboard()
  const tile = data?.tiles.find((x) => tileKey(x) === pane.tile)
  if (tile && tile.kind !== 'action') return <TileWidgetPane pane={pane} tile={tile as WidgetTile} />
  return (
    <Framed title={pane.title} hide={pane.hide_title}>
      {isPending ? <Loader size="sm" aria-label={t('common.loading')} /> : <Note>{t('dashboards.pane.tileGone')}</Note>}
    </Framed>
  )
}

/** A data widget in its pane: it fits the box at the level the box allows. "+N more" and the
 *  button open it large over the dashboard; Esc goes back. */
function TileWidgetPane({ pane, tile }: { pane: Extract<Pane, { kind: 'tile' }>; tile: WidgetTile }) {
  const { t } = useTranslation()
  const [big, setBig] = useState(false)
  const { data, error, isPending } = useWidget(tile)
  const title = pane.title ?? tile.label
  const link = data?.link && data.link.startsWith('/') ? data.link : ''
  return (
    <Framed title={title} hide={pane.hide_title} fit actions={data && (
      <>
        {link && (
          <Tooltip label={t('common.details')}>
            <ActionIcon component="a" href={link} variant="subtle" color="gray" size="sm" aria-label={t('widgets.kind.detailsNamed', { name: title })}>
              <IconExternalLink size={15} />
            </ActionIcon>
          </Tooltip>
        )}
        <Tooltip label={t('dashboards.pane.openBig')}>
          <ActionIcon variant="subtle" color="gray" size="sm" aria-label={t('dashboards.pane.openBigNamed', { name: title })} onClick={() => setBig(true)}>
            <IconArrowsMaximize size={15} />
          </ActionIcon>
        </Tooltip>
      </>
    )}>
      {isPending ? <Loader size="sm" aria-label={t('common.loading')} />
        : error && !data ? <Text size="sm" className="fb-tone-err fb-pane-note" role="alert">✕ {error.message}</Text>
          : data ? <FitWidget widget={data} pick={pane.type} pin={pane.level} onMore={() => setBig(true)} /> : null}
      {big && data && (
        <Modal opened onClose={() => setBig(false)} title={title} size="90%" centered classNames={{ body: 'fb-w-big' }}>
          <FitWidget widget={data} pick={pane.type} pin="l" />
        </Modal>
      )}
    </Framed>
  )
}

/** A rich widget. Small on the grid unless the pane is set to show it big; the button opens it big
 *  over the dashboard, with its filters and actions, without leaving the screen. */
function ViewPane({ pane }: { pane: Extract<Pane, { kind: 'view' }> }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const off = useFeaturesOff()
  const def = VIEWS.find((v) => v.id === pane.view)
  // A feature switched off (Settings > Features) has no data to show: say so instead of an error.
  const View = def && !(def.feature && off.includes(def.feature)) ? VIEW_COMPONENTS[def.id] : null
  const title = pane.title ?? (def ? t(def.label) : undefined)
  const big = !!pane.expanded
  const loading = <Loader size="sm" aria-label={t('common.loading')} />
  return (
    <Framed title={title} hide={pane.hide_title} actions={View && !big && (
      <Tooltip label={t('dashboards.pane.openBig')}>
        <ActionIcon variant="subtle" color="gray" aria-label={t('dashboards.pane.openBigNamed', { name: title ?? '' })}
          onClick={() => setOpen(true)}><IconArrowsMaximize size={16} /></ActionIcon>
      </Tooltip>
    )}>
      {View ? <Suspense fallback={loading}><View expanded={big} /></Suspense>
        : <Note>{def ? t('dashboards.pane.viewOff') : t('dashboards.pane.viewGone')}</Note>}
      {View && open && (
        <Modal opened onClose={() => setOpen(false)} title={title} size="90%" centered classNames={{ body: 'fb-view-big' }}>
          <Suspense fallback={loading}><View expanded /></Suspense>
        </Modal>
      )}
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
    case 'view': return <ViewPane pane={pane} />
    case 'text': return <TextPane pane={pane} />
    case 'private': return <Framed title={pane.title} hide={pane.hide_title}><Stack h="100%" justify="center" align="center"><Note>{t('dashboards.pane.private')}</Note></Stack></Framed>
    default: return <Framed title={pane.title} hide={pane.hide_title}><Stack h="100%" justify="center" align="center"><Note>{t('dashboards.pane.empty')}</Note></Stack></Framed>
  }
}
