import { Alert, Button, Group, Loader, Text } from '@mantine/core'
import { IconPrinter } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useHelpdeskQr } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

/** A printable sheet: one QR code per seat, each opening that seat's signed help page. */
export default function HelpdeskQr() {
  const { t } = useTranslation()
  const qr = useHelpdeskQr()
  return (
    <Layout title={t('incidents.qrTitle')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <div className="fb-no-print">
        <PageHead title={t('incidents.qrTitle')} desc={t('incidents.qrIntro')}
          actions={<Button leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>{t('incidents.print')}</Button>} />
      </div>
      {qr.error && (
        <Alert color="down" role="alert" mb="md">
          {t('common.error', { message: qr.error.message })}
        </Alert>
      )}
      {qr.isPending ? (
        <Loader size="sm" />
      ) : !qr.data?.seats.length ? (
        <Text c="dimmed">{t('incidents.qrNone')}</Text>
      ) : (
        <div className="fb-qr-sheet">
          {qr.data.seats.map((s) => (
            <figure key={s.seat} className="fb-qr">
              <img className="fb-qr-code" src={s.image} alt={t('incidents.qrAlt', { seat: s.seat })} />
              <figcaption>
                <Group gap={4} justify="center">
                  <strong>{s.seat}</strong>
                </Group>
                <span>{t('incidents.qrCaption')}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </Layout>
  )
}
