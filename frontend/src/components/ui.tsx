// The panel a list or form sits in, so pages look and behave like one app. The side panel, its
// sections and fields, and the loading, error and empty states come from @bitsandbricks/ui.
// From Hubra (by Mike): packages/ui/src/feedback.tsx, with Floorbit's tokens and texts.
import { Group, Paper, Text, Title } from '@mantine/core'
import type { CSSProperties, ReactNode } from 'react'

/** The bordered panel a list, a form or a group of facts sits in. With a ``title``, a header row
 *  with the title, an optional line under it and ``actions`` at the end. */
export function Panel({ title, titleId, desc, actions, children, padding = 'md', style, className, ...rest }: {
  title?: ReactNode; desc?: ReactNode; actions?: ReactNode; children?: ReactNode
  /** Names the panel by its title (aria-labelledby), for pages that list several. */
  titleId?: string
  /** 0 when the content brings its own (a table that runs to the edges). */
  padding?: 0 | 'sm' | 'md' | 'lg'; style?: CSSProperties; className?: string
  'aria-label'?: string; id?: string
}) {
  return (
    <Paper withBorder radius="lg" p={padding} style={style} className={className} component="section"
      aria-labelledby={title && titleId ? titleId : undefined} {...rest}>
      {(title || actions) && (
        <Group justify="space-between" align="flex-start" gap="sm" wrap="wrap" mb="sm"
          px={padding === 0 ? 'md' : undefined} pt={padding === 0 ? 'md' : undefined}>
          <div style={{ minWidth: 0, flex: '1 1 200px' }}>
            {title && <Title order={2} size="h4" id={titleId}>{title}</Title>}
            {desc && <Text size="sm" c="dimmed">{desc}</Text>}
          </div>
          {actions && <Group gap="xs" wrap="wrap">{actions}</Group>}
        </Group>
      )}
      {children}
    </Paper>
  )
}
