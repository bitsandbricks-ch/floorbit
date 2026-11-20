// The building blocks every crew page uses, so pages look and behave like one app: the panel a
// list or form sits in, the side panel for one item, and the loading, error and empty states.
// From Hubra (by Mike): packages/ui/src/feedback.tsx, with Floorbit's tokens and texts.
import { ActionIcon, Alert, Button, Center, Drawer, Group, Paper, Skeleton, Stack, Text, ThemeIcon, Title, useMatches } from '@mantine/core'
import { IconAlertTriangle, IconInbox, IconRefresh, IconX } from '@tabler/icons-react'
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

/** While a page's data loads: the shape of a page, not a spinner in a corner. ``lines`` is the
 *  small version for a side panel or a dashboard pane: a few text-high bars that fit any size.
 *  Spinners stay inside buttons only (#1017). */
export function LoadingState({ rows = 3, lines = false }: { rows?: number; lines?: boolean }) {
  const { t } = useTranslation()
  return (
    <Stack gap={lines ? 8 : 'sm'} aria-busy="true" aria-label={t('common.loading')} role="status">
      {Array.from({ length: rows }, (_, i) => lines
        ? <Skeleton key={i} h={12} w={`${[90, 70, 80][i % 3]}%`} radius="sm" />
        : <Skeleton key={i} h={i === 0 ? 120 : 64} radius="lg" />)}
    </Stack>
  )
}

/** A request that failed: what the server said, and a way to try again. */
export function ErrorBanner({ error, onRetry, mb }: { error: Error | string | null | undefined; onRetry?: () => void; mb?: string }) {
  const { t } = useTranslation()
  if (!error) return null
  const message = typeof error === 'string' ? error : error.message
  return (
    <Alert color="down" variant="light" role="alert" mb={mb} icon={<IconAlertTriangle size={16} />}>
      <Group gap="xs" align="center" wrap="nowrap">
        <Text size="sm" flex={1}>{t('common.error', { message })}</Text>
        {onRetry && (
          <Button variant="subtle" size="xs" color="down" leftSection={<IconRefresh size={16} />} onClick={onRetry}>
            {t('common.retry')}
          </Button>
        )}
      </Group>
    </Alert>
  )
}

/** Nothing here yet: say so, say why or what to do, and offer the one action that helps. */
export function EmptyState({ icon, title, desc, action }: {
  icon?: ReactNode; title: ReactNode; desc?: ReactNode; action?: ReactNode
}) {
  return (
    <Center py={48} px="md">
      <Stack align="center" gap={6}>
        <ThemeIcon size={52} radius="xl" variant="light" color="gray" mb={6}>{icon ?? <IconInbox size={24} />}</ThemeIcon>
        <Text fw={650} ta="center">{title}</Text>
        {desc && <Text size="sm" c="dimmed" maw={420} ta="center">{desc}</Text>}
        {action && <div style={{ marginTop: 8 }}>{action}</div>}
      </Stack>
    </Center>
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
