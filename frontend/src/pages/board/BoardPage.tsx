import { Button, Select } from '@mantine/core'
import { IconClock, IconMaximize, IconPencil, IconPin, IconPinnedOff } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useMemo, useState } from 'react'
import { useMediaQuery } from '@mantine/hooks'
import { Link, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { readBoot, useNavPrefs } from '@/nav/boot'
import { type Board, TIME_RANGES, type TimeRange, boardName } from '../dashboards/model'
import { ScreenContext } from '../dashboards/screen'
import { GridView } from '../dashboards/GridView'
import { useFillHeight } from '../dashboards/fill'
import '../dashboards/dashboards.css'

/** One dashboard inside the app's frame, with the sidebar: the same widgets as on a big screen,
 *  with buttons to pin it to the sidebar, change it, or open it full screen. */
export function BoardPage({ id, title, kicker }: { id: string; title?: string; kicker?: string }) {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const [prefs, setPrefs] = useNavPrefs(readBoot())
  const q = useQuery({ queryKey: qk.board(id), queryFn: () => get<Board>(`/api/dashboards/${encodeURIComponent(id)}`), refetchInterval: 60_000 })
  const name = title ?? (q.data ? boardName(t, q.data) : t('dashboards.title'))
  const fav = `dashboard:${id}`
  const pinned = prefs.favourites.includes(fav)
  const pin = () => setPrefs({ ...prefs, favourites: pinned ? prefs.favourites.filter((x) => x !== fav) : [...prefs.favourites, fav] })
  // The time shown: the viewer's pick (in the address, so it can be shared), else the dashboard's.
  const [params, setParams] = useSearchParams()
  const asked = params.get('range') as TimeRange | null
  const range = asked && TIME_RANGES.includes(asked) ? asked : q.data?.range
  const source = useMemo(() => ({ publicId: null, tiles: {}, hall: '', range }), [range])
  const pickRange = (v: string | null) => setParams((p) => {
    const next = new URLSearchParams(p)
    if (v && v !== 'auto') next.set('range', v)
    else next.delete('range')
    return next
  }, { replace: true })
  // Screen dashboards fit under the top bar like on a wall; phones always scroll (#923).
  const phone = useMediaQuery('(max-width: 48em)', false, { getInitialValueInEffect: false })
  const fit = !!q.data?.fit && !phone
  const [area, setArea] = useState<HTMLDivElement | null>(null)
  const height = useFillHeight(area, fit)
  return (
    <Layout title={name}>
      <PageHead
        title={name} kicker={kicker}
        actions={<>
          <Select aria-label={t('board.range')} w={170} allowDeselect={false} leftSection={<IconClock size={16} aria-hidden="true" />} value={range ?? 'auto'} onChange={pickRange}
            data={['auto', ...TIME_RANGES].map((r) => ({ value: r, label: r === 'auto' ? t('board.rangeAuto') : t(`dashboards.range.${r}`) }))} />
          <Button variant="default" onClick={pin} aria-pressed={pinned}
            leftSection={pinned ? <IconPinnedOff size={16} aria-hidden="true" /> : <IconPin size={16} aria-hidden="true" />}>
            {pinned ? t('board.unpin') : t('board.pin')}
          </Button>
          {canEdit && (
            <Button variant="default" component={Link} to={`/dashboards?edit=${encodeURIComponent(id)}`} leftSection={<IconPencil size={16} aria-hidden="true" />}>
              {t('board.edit')}
            </Button>
          )}
          <Button variant="default" component="a" href={`/dashboards/${encodeURIComponent(id)}${asked ? `?range=${asked}` : ''}`} leftSection={<IconMaximize size={16} aria-hidden="true" />}>
            {t('board.bigScreen')}
          </Button>
        </>}
      />
      {q.isPending && <LoadingState />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {q.data && (
        <div ref={setArea} className={`fb-board-inline${fit ? ' fit' : ''}`} style={fit && height ? { height } : undefined}>
          <ScreenContext.Provider value={source}>
            <GridView sections={q.data.sections} fit={fit} cycle={q.data.cycle} />
          </ScreenContext.Provider>
        </div>
      )}
    </Layout>
  )
}
