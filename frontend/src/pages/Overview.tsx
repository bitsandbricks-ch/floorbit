import { useTranslation } from 'react-i18next'
import { BoardPage } from './board/BoardPage'

/** The crew's start page: the built-in Overview dashboard inside the sidebar's frame, so it is
 *  made of the same widgets as every dashboard and can be changed like one. */
export default function Overview() {
  const { t } = useTranslation()
  return <BoardPage id="overview" title={t('overview.title')} kicker={t('overview.kicker')} />
}
