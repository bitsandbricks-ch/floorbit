import { Anchor, Group, Loader, Paper, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PluginPanelInfo, Widget } from '@/api/types'
import { WidgetBody } from '@/widgets/WidgetBody'
import { PluginIcon } from './icon'

export type PanelFor = 'seat' | 'switch' | 'device'

/** The plugins' boxes for one seat, switch or inventory device (`panels:` in plugin.yaml). Each
 *  box loads on its own, so a slow or broken plugin only shows its own error. Nothing when no
 *  plugin that is on has a panel here. */
export function PluginPanels({ on, target, frame = (c) => c }: {
  on: PanelFor; target: string; frame?: (children: ReactNode) => ReactNode
}) {
  const list = useQuery({
    queryKey: qk.pluginPanels(on),
    queryFn: () => get<{ panels: PluginPanelInfo[] }>(`/api/plugins/panels?on=${on}`),
    staleTime: 60_000,
  })
  const panels = list.data?.panels ?? []
  if (panels.length === 0) return null
  // `frame` puts the boxes in the page's own section style, only when there are any.
  return frame(
    <Stack gap="xs">
      {panels.map((p) => <PanelBox key={`${p.plugin}/${p.id}`} panel={p} target={target} />)}
    </Stack>,
  )
}

function PanelBox({ panel, target }: { panel: PluginPanelInfo; target: string }) {
  const { t } = useTranslation()
  const q = useQuery({
    queryKey: qk.pluginPanel(panel.url, target),
    queryFn: () => get<Widget>(`${panel.url}?target=${encodeURIComponent(target)}`),
    refetchInterval: Math.max(10, panel.refresh) * 1000,
    retry: false,
  })
  const w = q.data
  return (
    <Paper withBorder radius="md" p="sm" component="section" aria-label={panel.label}>
      <Stack gap={6}>
        <Group gap={8} wrap="nowrap">
          <PluginIcon name={panel.icon} size={22} />
          <Text size="sm" fw={600}>{panel.label}</Text>
          <Text size="xs" c="dimmed" ml="auto">{panel.plugin_name}</Text>
        </Group>
        {q.isPending ? (
          <Loader size="xs" aria-label={t('common.loading')} />
        ) : q.error && !w ? (
          <Text size="sm" className="fb-tone-err" role="alert">✕ {q.error.message}</Text>
        ) : w ? (
          <>
            <WidgetBody widget={w} />
            {w.sub && <Text size="xs" c="dimmed">{w.sub}</Text>}
            {w.link && <Anchor href={w.link} size="sm">{t('common.details')}</Anchor>}
          </>
        ) : null}
      </Stack>
    </Paper>
  )
}
