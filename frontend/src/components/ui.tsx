// The building blocks every crew page uses, so pages look and behave like one app: the panel a
// list or form sits in, and the side panel for one item. Loading, error and empty states come from @bitsandbricks/ui.
// From Hubra (by Mike): packages/ui/src/feedback.tsx, with Floorbit's tokens and texts.
import { ActionIcon, Drawer, Group, Paper, Text, Title, useMatches } from '@mantine/core'
import { IconX } from '@tabler/icons-react'
import type { CSSProperties, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/** The bordered panel a list, a form or a group of facts sits in. With a ``title``, a header row
 *  with the title, an optional line under it and ``actions`` at the end. */
export function Panel({ title, desc, actions, children, padding = 'md', style, className, ...rest }: {
  title?: ReactNode; desc?: ReactNode; actions?: ReactNode; children?: ReactNode
  /** 0 when the content brings its own (a table that runs to the edges). */
  padding?: 0 | 'sm' | 'md' | 'lg'; style?: CSSProperties; className?: string
  'aria-label'?: string; id?: string
}) {
  return (
    <Paper withBorder radius="lg" p={padding} style={style} className={className} component="section" {...rest}>
      {(title || actions) && (
        <Group justify="space-between" align="flex-start" gap="sm" wrap="wrap" mb="sm"
          px={padding === 0 ? 'md' : undefined} pt={padding === 0 ? 'md' : undefined}>
          <div style={{ minWidth: 0, flex: '1 1 200px' }}>
            {title && <Title order={2} size="h4">{title}</Title>}
            {desc && <Text size="sm" c="dimmed">{desc}</Text>}
          </div>
          {actions && <Group gap="xs" wrap="wrap">{actions}</Group>}
        </Group>
      )}
      {children}
    </Paper>
  )
}

/** One item's details beside the list it came from: from the right on desktops, the whole width
 *  on phones. Every page opens its items the same way. */
export function SidePanel({ title, subtitle, actions, opened = true, onClose, width = 440, footer, children }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; opened?: boolean; onClose: () => void
  width?: number; footer?: ReactNode; children: ReactNode
}) {
  const { t } = useTranslation()
  const size = useMatches({ base: '100%', sm: width }, { getInitialValueInEffect: false })
  return (
    <Drawer.Root opened={opened} onClose={onClose} position="right" size={size} padding={0}>
      <Drawer.Overlay backgroundOpacity={0.18} />
      <Drawer.Content className="fb-sidepanel">
        <div className="fb-sidepanel-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <Drawer.Title fw={650} fz="md" style={{ overflowWrap: 'anywhere' }}>{title}</Drawer.Title>
            {subtitle && <Text size="sm" c="dimmed">{subtitle}</Text>}
          </div>
          <Group gap={4} wrap="nowrap">
            {actions}
            <ActionIcon variant="subtle" color="gray" onClick={onClose} aria-label={t('common.close')}><IconX size={18} /></ActionIcon>
          </Group>
        </div>
        <div className="fb-sidepanel-body">{children}</div>
        {footer && <div className="fb-sidepanel-foot">{footer}</div>}
      </Drawer.Content>
    </Drawer.Root>
  )
}

/** A block of a side panel, with a small heading. */
export function PanelSection({ label, right, children }: { label?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="fb-panel-section">
      {(label || right) && (
        <div className="fb-panel-section-head">
          <span className="fb-panel-label">{label}</span>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

/** A label above a value, for an item's facts. */
export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div className="fb-field-label">{label}</div>
      <div className="fb-field-value">{children}</div>
    </div>
  )
}
