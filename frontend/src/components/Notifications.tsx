import { ActionIcon, Button, Tooltip } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconArrowRight, IconBellCog } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useMe, useProblems } from '@/api/queries'
import { ago } from '@/lib/time'
import { FilterBar, LoadingState, Pager, SidePanel, StatusBit, type FilterGroup } from '@bitsandbricks/ui'
import { NotifyDetail } from './notifications/NotifyDetail'
import { countGroups, filterItems, notifyItems, pageOf, PER_PAGE, type NotifyFilter } from './notifications/list'
import { NotifySettings } from './NotifySettings'
import './notifications/Notifications.css'

const FILTERS: NotifyFilter[] = ['all', 'down', 'warn', 'seats']

/** The bell's panel (#1388): what needs a look right now, worst first, paged at 50, and the picked
 *  one's details beside the list. On a phone the details replace the list until "Back". */
export function Notifications({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const me = useMe().data
  const q = useProblems()
  const phone = useMediaQuery('(max-width: 48em)', false, { getInitialValueInEffect: false })
  const [settings, setSettings] = useState(false)
  const [filter, setFilter] = useState<NotifyFilter>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [picked, setPicked] = useState<string | null>(null)

  const all = useMemo(() => notifyItems(q.data), [q.data])
  const counts = useMemo(() => countGroups(all), [all])
  const shown = useMemo(() => filterItems(all, filter, search), [all, filter, search])
  // A page past the end (the list got shorter while open) shows the last one.
  const pages = Math.max(1, Math.ceil(shown.length / PER_PAGE))
  const onPage = Math.min(page, pages)
  const rows = shown.slice((onPage - 1) * PER_PAGE, onPage * PER_PAGE)
  // The picked one while it is still listed; on a computer the first row otherwise, so the details are never empty.
  const pickedIndex = shown.findIndex((it) => it.p.id === picked)
  const index = pickedIndex >= 0 ? pickedIndex : phone || !rows.length ? -1 : (onPage - 1) * PER_PAGE
  const current = index >= 0 ? shown[index] : null
  const step = (by: number) => {
    const next = shown[index + by]
    if (!next) return
    setPicked(next.p.id)
    setPage(pageOf(index + by))
  }
  const groups: FilterGroup[] = [{
    key: 'show', label: t('notifications.show'), value: filter, defaultValue: 'all',
    onChange: (v) => { setFilter(v as NotifyFilter); setPage(1) },
    options: FILTERS.map((f) => ({ value: f, label: t(`notifications.filter.${f}`), count: counts[f] })),
  }]
  const leave = () => { setPicked(null); onClose() }
  const listShown = !phone || !current
  return (
    <>
      <SidePanel
        opened={opened} onClose={leave} title={t('nav.notifications')} padded={false}
        width={phone ? undefined : 960} resizable={{ storageKey: 'floorbit:notifications-width', min: 640 }}
        eyebrow={q.data ? t('notifications.eyebrow', { ago: ago(q.data.checked_at), count: all.length }) : undefined}
        onPrev={current && index > 0 ? () => step(-1) : undefined}
        onNext={current && index < shown.length - 1 ? () => step(1) : undefined}
        actions={<>
          {me?.user && (
            <Tooltip label={t('nav.notify.settings')}>
              <ActionIcon variant="default" onClick={() => setSettings(true)} aria-label={t('nav.notify.settings')}>
                <IconBellCog size={16} aria-hidden="true" />
              </ActionIcon>
            </Tooltip>
          )}
          <Button component={Link} to="/problems" size="xs" variant="subtle" onClick={leave}
            rightSection={<IconArrowRight size={14} aria-hidden="true" />}>{t('nav.notify.all')}</Button>
        </>}
      >
        <div className={`fb-notify${current && !phone ? ' has-detail' : ''}`}>
          {listShown && (
            <div className="fb-notify-list">
              {all.length > 0 && (
                <div className="fb-notify-filters">
                  <FilterBar search={search} onSearchChange={(v) => { setSearch(v); setPage(1) }}
                    searchLabel={t('notifications.search')} groups={groups} />
                </div>
              )}
              {q.isPending ? <LoadingState rows={6} /> : (
                <>
                  {all.length === 0 && (
                    <div className="fb-notify-empty"><span className="bnb-bit is-ok" aria-hidden="true" />{t('nav.notify.empty')}</div>
                  )}
                  {all.length > 0 && shown.length === 0 && <div className="fb-notify-empty">{t('notifications.noMatch')}</div>}
                  <ul className="fb-notify-rows" aria-label={t('nav.notifications')}>
                    {rows.map(({ p }) => (
                      <li key={p.id}>
                        <button type="button" className={`fb-notify-row${current?.p.id === p.id ? ' is-picked' : ''}`}
                          aria-current={current?.p.id === p.id ? 'true' : undefined} onClick={() => setPicked(p.id)}>
                          <StatusBit state={p.level} />
                          <span className="fb-notify-text">
                            <b>{p.title}</b>
                            {p.where && <small>{p.where}</small>}
                          </span>
                          {p.since ? <time className="fb-notify-when">{ago(p.since)}</time> : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="fb-notify-pager">
                    <Pager page={onPage} perPage={PER_PAGE} total={shown.length} onPage={setPage} />
                  </div>
                </>
              )}
            </div>
          )}
          {current && (
            <div className="fb-notify-detail">
              <NotifyDetail key={current.p.id} id={current.p.id} onLeave={leave} onBack={phone ? () => setPicked(null) : undefined} />
            </div>
          )}
        </div>
      </SidePanel>
      {settings && <NotifySettings opened onClose={() => setSettings(false)} />}
    </>
  )
}
