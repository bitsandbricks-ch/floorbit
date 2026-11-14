import { Anchor, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Layout } from '@/components/Layout'

export default function NotFound() {
  const { t } = useTranslation()
  return (
    <Layout title="404" back={{ href: '/', label: t('common.floorPlan') }}>
      <Text mb="sm">{t('common.notFound')}</Text>
      <Anchor href="/">{t('common.backToPlan')}</Anchor>
    </Layout>
  )
}
