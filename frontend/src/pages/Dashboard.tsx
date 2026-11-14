import { Alert, Anchor, Loader, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { useDashboard, useWidget } from '@/api/queries'
import type { ActionResult, ActionTile, Tile, WidgetTile } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { WidgetBody } from '@/widgets/WidgetBody'

function TileFrame({ title, from, wide, children }: { title: string; from: string; wide?: boolean; children: React.ReactNode }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" style={wide ? { gridColumn: '1 / -1' } : undefined} component="section">
      <Stack gap={10}>
        <div>
          <Title order={3} fz="md">
            {title}
          </Title>
          <Text size="xs" c="dimmed">
            {t('dashboard.from', { plugin: from })}
          </Text>
        </div>
        {children}
      </Stack>
    </Paper>
  )
}

function WidgetCard({ tile }: { tile: WidgetTile }) {
  const { t } = useTranslation()
  const { data, error, isPending } = useWidget(tile)
  return (
    <TileFrame title={tile.label} from={tile.plugin_name} wide={tile.size === 'wide'}>
      {isPending ? (
        <Loader size="sm" aria-label={t('common.loading')} />
      ) : error && !data ? (
        <Text size="sm" className="fb-tone-err" role="alert">
          ✕ {error.message}
        </Text>
      ) : data ? (
        <>
          <WidgetBody widget={data} />
          {data.sub && (
            <Text size="xs" c="dimmed">
              {data.sub}
            </Text>
          )}
          {data.link && (
            <Anchor href={data.link} size="sm">
              {t('common.details')}
            </Anchor>
          )}
        </>
      ) : null}
    </TileFrame>
  )
}

function ActionCard({ tile }: { tile: ActionTile }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const run = useMutation({
    mutationFn: () => post<ActionResult>(tile.url),
    onSuccess: (r) => setResult({ ok: true, text: r.message }),
    onError: (e) => setResult({ ok: false, text: e.message }),
  })
  return (
    <TileFrame title={tile.label} from={tile.plugin_name}>
      <ConfirmButton label={tile.label} danger={tile.danger} loading={run.isPending} onConfirm={() => run.mutate()} />
      <Text size="sm" role="status" className={result ? (result.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {run.isPending ? t('common.working') : result ? `${result.ok ? '✓' : '✕'} ${result.text}` : ''}
      </Text>
    </TileFrame>
  )
}

export function TileGrid({ tiles }: { tiles: Tile[] }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md" aria-live="polite">
      {tiles.map((tile) =>
        tile.kind === 'action' ? (
          <ActionCard key={`${tile.plugin}/a/${tile.id}`} tile={tile} />
        ) : (
          <WidgetCard key={`${tile.plugin}/w/${tile.id}`} tile={tile} />
        ),
      )}
    </SimpleGrid>
  )
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { data, error, isPending } = useDashboard()
  return (
    <Layout title={t('dashboard.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      {isPending && <Loader aria-label={t('common.loading')} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && data.tiles.length === 0 && (
        <Paper withBorder radius="lg" p="lg">
          <Text>{t('dashboard.empty')}</Text>
          <Anchor href="/settings/plugins" mt="sm" display="inline-block">
            {t('dashboard.emptyLink')}
          </Anchor>
        </Paper>
      )}
      {data && data.tiles.length > 0 && <TileGrid tiles={data.tiles} />}
    </Layout>
  )
}
