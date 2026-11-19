import { Button } from '@mantine/core'
import { IconArrowLeft, IconFolder, IconTag, IconStack2 } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { EmptyState, LoadingState } from '@/components/ui'
import { DeviceIcon } from './icons'
import { scopePath } from './model'
import { useInventoryGroups } from './scope'
import { ScopeEditor, type ScopeTarget } from './ScopeEditor'

/** A group's, a tag's or the defaults' own page: what the devices in it inherit.
 *  /inventory/groups/<id> (``new``, with ``?parent=``), /inventory/tags/<id>, /inventory/defaults. */
export default function ScopePage({ kind }: { kind: 'group' | 'tag' | 'defaults' }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const id = useParams().id ?? ''
  const parent = useSearchParams()[0].get('parent')
  const groups = useInventoryGroups()
  const overview = groups.data
  const isNew = id === 'new'
  const group = kind === 'group' ? overview?.groups.find((g) => g.id === id) ?? null : null
  const tag = kind === 'tag' ? overview?.tags.find((x) => x.id === id) ?? null : null
  const item = group ?? tag
  const target: ScopeTarget | null = !overview ? null
    : kind === 'defaults' ? { kind: 'defaults' }
      : kind === 'group' ? { kind: 'group', item: group, parent } : { kind: 'tag', item: tag }
  const missing = !!overview && kind !== 'defaults' && !isNew && !item
  const title = kind === 'defaults' ? t('inventory.groups.all')
    : item ? item.name : t(kind === 'group' ? 'inventory.groups.new' : 'inventory.tags.new')
  const kicker = kind === 'group' ? t('inventory.groups.subtitle', { count: group?.devices ?? 0 })
    : kind === 'tag' ? t('inventory.tags.subtitle', { count: tag?.used ?? 0 }) : t('inventory.groups.allHint')
  const icon = item?.icon ? <DeviceIcon icon={item.icon} color={item.color} size={28} />
    : kind === 'tag' ? <IconTag size={26} /> : kind === 'group' ? <IconFolder size={26} /> : <IconStack2 size={26} />

  return (
    <Layout title={title}>
      {groups.error || missing ? (
        <EmptyState title={t('inventory.page.notFound')} desc={groups.error?.message}
          action={<Button component={Link} to="/inventory" variant="default" leftSection={<IconArrowLeft size={16} />}>{t('inventory.page.back')}</Button>} />
      ) : !target || !overview ? <LoadingState rows={6} /> : (
        <>
          <PageHead icon={icon} kicker={kicker} title={title} />
          <ScopeEditor key={`${kind}-${id}`} target={target} overview={overview}
            onDeleted={() => navigate('/inventory')}
            onSaved={(saved) => {
              if (saved.kind !== 'defaults' && saved.item) navigate(scopePath(saved.kind, saved.item.id), { replace: true })
            }} />
        </>
      )}
    </Layout>
  )
}
