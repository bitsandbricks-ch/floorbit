import { Menu, SegmentedControl, UnstyledButton } from '@mantine/core'
import { IconBookmark, IconDots, IconEdit, IconFilter, IconList, IconMap, IconStack2, IconTopologyStar3 } from '@tabler/icons-react'
import type { ComponentPropsWithoutRef, ReactNode, Ref } from 'react'
import { useTranslation } from 'react-i18next'
import './PhoneControls.css'

export type PlanView = 'map' | 'list' | 'topology'

/** The floor plan's controls on a phone (Mike, 2026-11-26, "map first"): no bar over the plan,
 *  a floating search with the online count, a small Map/List/Topology switch, and a dock at thumb
 *  height whose buttons open sheets and menus. The plan keeps the rest of the screen. */
export function PhoneControls({ search, online, total, view, onView, layersOn, onLayers, problems, onProblems, views, more, onEdit }: {
  /** The search form (FloorPlan's, so the keys and results stay the same). */
  search?: ReactNode
  online: number; total: number
  view: PlanView; onView: (v: PlanView) => void
  /** How many layers are on; no Layers button without onLayers (list and topology). */
  layersOn: number; onLayers?: () => void
  problems: number; onProblems: () => void
  /** Saved views, a menu whose target is the dock button given to it. */
  views?: (target: ReactNode) => ReactNode
  /** The More menu's entries. */
  more: ReactNode
  /** Editing, for those who may: a dock button of its own, not an entry at the end of More (Mike, 2026-11-26). */
  onEdit?: () => void
}) {
  const { t } = useTranslation()
  const icon = (v: PlanView) => v === 'map' ? <IconMap size={18} /> : v === 'list' ? <IconList size={18} /> : <IconTopologyStar3 size={18} />
  const label = (v: PlanView) => v === 'topology' ? t('topology.title') : t(`plan.list.${v}`)
  const dock = view !== 'topology'
  return (
    <div className={`fb-phone-ctl is-${view}`}>
      <div className="fb-phone-top">
        {search && (
          <div className="fb-phone-search">
            {search}
            <span className="fb-phone-count" aria-label={`${online} / ${total} ${t('plan.online')}`}><i aria-hidden="true" />{online}/{total}</span>
          </div>
        )}
        <SegmentedControl className="fb-phone-views" orientation="vertical" size="xs" value={view} onChange={(v) => onView(v as PlanView)}
          aria-label={t('plan.list.view')}
          data={(['map', 'list', 'topology'] as PlanView[]).map((v) => ({ value: v, label: <span title={label(v)} aria-label={label(v)}>{icon(v)}</span> }))} />
      </div>
      {dock && (
        <nav className="fb-phone-dock" aria-label={t('planPhone.dock')}>
          {onLayers && <DockButton icon={<IconStack2 size={20} />} label={t('plan.side.layers')} badge={layersOn || undefined} onClick={onLayers} />}
          <DockButton icon={<IconFilter size={20} />} label={t('plan.side.problems')} badge={problems || undefined} bad onClick={onProblems} />
          {views?.(<DockButton icon={<IconBookmark size={20} />} label={t('planPhone.views')} />)}
          {onEdit && <DockButton icon={<IconEdit size={20} />} label={t('planPhone.editShort')} onClick={onEdit} />}
          <Menu position="top-end" withinPortal width={260}>
            <Menu.Target>
              <DockButton icon={<IconDots size={20} />} label={t('planPhone.more')} />
            </Menu.Target>
            <Menu.Dropdown>{more}</Menu.Dropdown>
          </Menu>
        </nav>
      )}
    </div>
  )
}

function DockButton({ icon, label, badge, bad, ref, className, ...rest }: {
  icon: ReactNode; label: string; badge?: number; bad?: boolean; ref?: Ref<HTMLButtonElement>
} & ComponentPropsWithoutRef<'button'>) {
  return (
    <UnstyledButton ref={ref} {...rest} className={className ? `fb-dock-btn ${className}` : 'fb-dock-btn'}>
      <span className="fb-dock-icon">{icon}{badge ? <span className={bad ? 'fb-dock-badge bad' : 'fb-dock-badge'}>{badge}</span> : null}</span>
      <span>{label}</span>
    </UnstyledButton>
  )
}
