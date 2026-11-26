import { Group, Paper, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import '../Plugins.css'

/** One card on Settings > Plugins, the same slots for every kind (#1435): name and state at the
 *  top, one line on what it does, anything more, then where it comes from and its switch. */
export function PluginCard({ id, head, badge, about, foot, children, ...rest }: {
  id: string; head: ReactNode; badge: ReactNode; about: string; foot: ReactNode; children?: ReactNode
  'data-plugin'?: string; 'data-feature'?: string; 'data-cap'?: string
}) {
  return (
    <Paper withBorder radius="lg" p="md" component="li" id={id} className="fb-plugin-card" {...rest}>
      <Group justify="space-between" wrap="nowrap" gap="sm" align="center">
        <Group gap="sm" wrap="nowrap" miw={0}>{head}</Group>
        {badge}
      </Group>
      <Text size="sm" c="dimmed" lineClamp={1} title={about}>{about}</Text>
      {children}
      <Group justify="space-between" wrap="nowrap" gap="sm" className="fb-plugin-card-foot">{foot}</Group>
    </Paper>
  )
}

