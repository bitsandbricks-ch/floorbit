import { Button } from '@mantine/core'
import { IconMaximize, IconPencil, IconPin, IconPinnedOff } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { readBoot, useNavPrefs } from '@/nav/boot'
import { type Board, boardName } from '../dashboards/model'
import { ScreenContext } from '../dashboards/screen'
import { GridView } from '../dashboards/GridView'
import '../dashboards/dashboards.css'

const SOURCE = { publicId: null, tiles: {}, hall: '' }

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
  return (
    <Layout title={name}>
      <PageHead
        title={name} kicker={kicker}
        actions={<>
          <Button variant="default" onClick={pin} aria-pressed={pinned}
            leftSection={pinned ? <IconPinnedOff size={16} aria-hidden="true" /> : <IconPin size={16} aria-hidden="true" />}>
            {pinned ? t('board.unpin') : t('board.pin')}
          </Button>
          {canEdit && (
            <Button variant="default" component={Link} to={`/dashboards?edit=${encodeURIComponent(id)}`} leftSection={<IconPencil size={16} aria-hidden="true" />}>
              {t('board.edit')}
            </Button>
          )}
          <Button variant="default" component="a" href={`/dashboards/${encodeURIComponent(id)}`} leftSection={<IconMaximize size={16} aria-hidden="true" />}>
            {t('board.bigScreen')}
          </Button>
        </>}
      />
      {q.isPending && <LoadingState />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {q.data && (
        <div className="fb-board-inline">
          <ScreenContext.Provider value={SOURCE}>
            <GridView sections={q.data.sections} fit={false} cycle={q.data.cycle} />
          </ScreenContext.Provider>
        </div>
      )}
    </Layout>
  )
}
