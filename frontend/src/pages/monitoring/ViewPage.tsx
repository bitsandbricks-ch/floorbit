import { Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { LoadingState } from '@bitsandbricks/ui'
import { type MonitoringPage, PAGE_BODY, PAGE_LABEL } from './pages'

/** A Monitoring page (Health, Wi-Fi, DNS, Traffic, ...): its body with the page's header around
 *  it. The sentence under the title is ``<view>.intro``. */
export default function ViewPage({ view }: { view: MonitoringPage }) {
  const { t } = useTranslation()
  const View = PAGE_BODY[view]
  const title = t(PAGE_LABEL[view])
  return (
    <Layout title={title}>
      <PageHead title={title} desc={t(`${view}.intro`)} />
      <Suspense fallback={<LoadingState rows={3} />}><View expanded /></Suspense>
    </Layout>
  )
}
