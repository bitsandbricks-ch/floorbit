import { Anchor, Button, Group, Select, Text, TextInput } from '@mantine/core'
import { IconPrinter } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { useHelpdeskQr } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { parseSeats, seatBlock } from './incidents/qrFilter'
import { ErrorBanner, LoadingState } from '@/components/ui'

/** A printable sheet: one QR code per seat, each opening that seat's signed help page. */
export default function HelpdeskQr() {
  const { t } = useTranslation()
  const qr = useHelpdeskQr()
  // The seat and block panels on the Seats page link here with ?seats= or ?block= (issue #380).
  const [params] = useSearchParams()
  const [block, setBlock] = useState<string | null>(params.get('block')?.toUpperCase() || null)
  const [only, setOnly] = useState(params.get('seats') ?? '')
  const seats = useMemo(() => qr.data?.seats ?? [], [qr.data])
  // Reprinting a torn sticker or one rebuilt block shouldn't mean printing the whole hall.
  const blocks = useMemo(() => [...new Set(seats.map((s) => seatBlock(s.seat)).filter(Boolean))], [seats])
  const wanted = parseSeats(only)
  const shown = seats.filter((s) => (!block || seatBlock(s.seat) === block) && (!wanted.size || wanted.has(s.seat)))
  const filtered = !!block || wanted.size > 0
  // Shown so the crew sees before printing whether phones will reach that address (QR_URL setting).
  const opens = (seats[0]?.url ?? '').replace(/^(https?:\/\/[^/]+).*$/, '$1')
  const checkinAt = qr.data?.checkin?.address || (qr.data?.checkin?.url ?? '').replace(/^https?:\/\//, '')
  return (
    <Layout title={t('incidents.qrTitle')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <div className="fb-no-print">
        <PageHead title={t('incidents.qrTitle')} desc={t('incidents.qrIntro')}
          actions={<Button leftSection={<IconPrinter size={16} />} disabled={!shown.length} onClick={() => window.print()}>
            {t('incidents.print')}</Button>} />
        {seats.length > 0 && (
          <Group align="flex-end" gap="sm" mb="md" wrap="wrap">
            {blocks.length > 1 && (
              <Select label={t('incidents.qrBlock')} placeholder={t('incidents.qrAllBlocks')} data={blocks} value={block}
                onChange={setBlock} clearable w={160} />
            )}
            <TextInput label={t('incidents.qrOnly')} placeholder="D-6, D-7" value={only}
              onChange={(e) => setOnly(e.currentTarget.value)} w={240} />
            <Text size="sm" c="dimmed" aria-live="polite">
              {filtered ? t('incidents.qrShown', { count: shown.length, total: seats.length }) : t('incidents.qrAll', { count: seats.length })}
            </Text>
          </Group>
        )}
        {opens && (
          <Text size="sm" c="dimmed" mb="md" data-testid="qr-opens">
            {t('incidents.qrOpens', { address: opens })}{' '}
            <Anchor component={Link} to="/settings" size="sm">{t('incidents.qrChangeAddress')}</Anchor>
          </Text>
        )}
      </div>
      <ErrorBanner error={qr.error} mb="md" onRetry={() => void qr.refetch()} />
      {qr.isPending ? (
        <LoadingState lines />
      ) : !seats.length ? (
        <Text c="dimmed">{t('incidents.qrNone')}</Text>
      ) : !shown.length ? (
        <Text c="dimmed">{t('incidents.qrNoMatch')}</Text>
      ) : (
        <div className="fb-qr-sheet">
          {shown.map((s) => (
            <figure key={s.seat} className="fb-qr">
              <img className="fb-qr-code" src={s.image} alt={t('incidents.qrAlt', { seat: s.seat })} />
              <figcaption>
                <Group gap={4} justify="center">
                  <strong>{s.seat}</strong>
                </Group>
                <span>{t('incidents.qrCaption')}</span>
                {s.pin && (
                  // A PC has no camera: the address to type and the PIN that names this seat.
                  <span className="fb-qr-pin">
                    <span>{t('incidents.qrCheckin', { address: checkinAt })}</span>
                    <span>PIN <b>{s.pin}</b></span>
                  </span>
                )}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </Layout>
  )
}
