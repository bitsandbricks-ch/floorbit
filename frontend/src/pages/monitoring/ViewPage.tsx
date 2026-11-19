import { Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { LoadingState } from '@/components/ui'
import { VIEWS, VIEW_COMPONENTS } from '@/widgets/views'

/** A Monitoring page (Health, Wi-Fi, DNS, Traffic, ...): the same view a dashboard pane shows,
 *  at its expanded size with the page's header around it. One component per view, so a page and
 *  its widget never drift apart. The sentence under the title is ``<view>.intro``. */
export default function ViewPage({ view }: { view: string }) {
  const { t } = useTranslation()
  const def = VIEWS.find((v) => v.id === view)!
  const View = VIEW_COMPONENTS[view]
  const title = t(def.label)
  return (
    <Layout title={title}>
      <PageHead title={title} desc={t(`${view}.intro`)} />
      <Suspense fallback={<LoadingState />}><View expanded /></Suspense>
    </Layout>
  )
}
