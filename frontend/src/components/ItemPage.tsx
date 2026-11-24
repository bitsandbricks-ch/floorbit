import { Button, Group, Text } from '@mantine/core'
import { IconArrowLeft } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ConfirmButton } from './ConfirmButton'
import { Layout } from './Layout'
import { PageHead } from './PageHead'
import { EmptyState, LoadingState, Panel } from './ui'

/** One thing on its own page (#1018): a link back to its list, its name with an icon and a line
 *  about it in the top bar, then its parts. While it loads the page shows its shape; when it is gone
 *  it says so and offers the way back. Edit dialogs move here area by area: a page has a link and
 *  survives a reload, a dialog doesn't. */
export function ItemPage({ title, fallbackTitle, back, loading, missing, icon, kicker, actions, children }: {
  /** The item's name, once loaded. */
  title?: string
  /** The tab title while loading or when the item is gone, usually the list's name. */
  fallbackTitle: string
  back: { href: string; label: string }
  loading: boolean
  /** Set when the item doesn't exist (or can't be loaded): the reason, if there is one. */
  missing?: { title: string; desc?: ReactNode } | null
  icon?: ReactNode
  kicker?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <Layout title={(!missing && title) || fallbackTitle} back={back}>
      {missing ? (
        <EmptyState title={missing.title} desc={missing.desc}
          action={<Button component={Link} to={back.href} variant="default" leftSection={<IconArrowLeft size={16} />}>{back.label}</Button>} />
      ) : loading || !title ? <LoadingState rows={6} /> : (
        <>
          <PageHead icon={icon} kicker={kicker} title={title} actions={actions} />
          {children}
        </>
      )}
    </Layout>
  )
}

/** The last panel of an item's page: what removing it does, and the button that asks first. */
export function DangerZone({ label, question, desc, onConfirm, loading }: {
  label: string; question: string; desc?: ReactNode; onConfirm: () => void; loading?: boolean
}) {
  const { t } = useTranslation()
  return (
    <Panel title={t('item.danger')} className="fb-danger-zone">
      {desc && <Text size="sm" c="dimmed" mb="sm">{desc}</Text>}
      <Group>
        <ConfirmButton variant="default" danger label={label} question={question} onConfirm={onConfirm} loading={loading} />
      </Group>
    </Panel>
  )
}
