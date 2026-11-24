// Plugin tiles (issue #11) on the shared cards: Floorbit adds its query, its POST and the
// "from <plugin>" line with the plugin's translated name.
import { SimpleGrid } from '@mantine/core'
import { ActionCard, WidgetCard } from '@bitsandbricks/widgets'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { useWidget } from '@/api/queries'
import type { ActionResult, ActionTile, Tile, WidgetTile } from '@/api/types'
import { pluginName } from '@/lib/pluginName'

const run = (tile: ActionTile) => post<ActionResult>(tile.url)

function useFrom(tile: Tile) {
  const { t } = useTranslation()
  return t('dashboard.from', { plugin: pluginName(t, tile.plugin, tile.plugin_name) })
}

export function PluginWidgetCard({ tile }: { tile: WidgetTile }) {
  const { t } = useTranslation()
  return <WidgetCard tile={tile} state={useWidget(tile)} from={useFrom(tile)} detailsLabel={t('common.details')} />
}

function PluginActionCard({ tile }: { tile: ActionTile }) {
  return <ActionCard tile={tile} run={run} from={useFrom(tile)} />
}

export function TileGrid({ tiles, columns = 3 }: { tiles: Tile[]; columns?: number }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: Math.min(2, columns), lg: columns }} spacing="md" aria-live="polite">
      {tiles.map((tile) =>
        tile.kind === 'action' ? (
          <PluginActionCard key={`${tile.plugin}/a/${tile.id}`} tile={tile} />
        ) : (
          <PluginWidgetCard key={`${tile.plugin}/w/${tile.id}`} tile={tile} />
        ),
      )}
    </SimpleGrid>
  )
}
