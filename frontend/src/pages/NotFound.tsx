import { Anchor } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'

export default function NotFound() {
  const { t } = useTranslation()
  return (
    <Layout title="404" back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title="404" desc={t('common.notFound')} />
      <Anchor href="/">{t('common.backToPlan')}</Anchor>
    </Layout>
  )
}
