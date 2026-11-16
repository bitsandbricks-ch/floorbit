import { IconCircleCheck, IconDatabaseOff } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useDatabaseDown } from '@/api/databaseHealth'

function duration(seconds: number, lang: string): string {
  const fmt = (v: number, unit: 'second' | 'minute' | 'hour') =>
    new Intl.NumberFormat(lang, { style: 'unit', unit, unitDisplay: 'long' }).format(v)
  if (seconds < 60) return fmt(Math.max(1, seconds), 'second')
  if (seconds < 3600) return fmt(Math.floor(seconds / 60), 'minute')
  return fmt(Math.floor(seconds / 3600), 'hour')
}

/** The banner on every crew page while the database is away (docs/database.md), and a short
 *  "back" once it answers again. Plain markup, no Mantine: the pages Flask draws load only the
 *  sidebar's code. ``floating`` for those pages, over their own top bar. */
export function DatabaseBanner({ floating = false }: { floating?: boolean }) {
  const { t, i18n } = useTranslation()
  const { down, downFor, back } = useDatabaseDown()
  if (!down && !back) return null
  const cls = `fb-db-banner ${down ? 'is-down' : 'is-back'}${floating ? ' is-floating' : ''}`
  return (
    <div role={down ? 'alert' : 'status'} className={cls}>
      {down ? <IconDatabaseOff size={18} aria-hidden="true" /> : <IconCircleCheck size={18} aria-hidden="true" />}
      <div>
        <p className="fb-db-banner-title">{t(down ? 'database.downTitle' : 'database.backTitle')}</p>
        <p>{t(down ? 'database.downText' : 'database.backText')}</p>
        {down && downFor > 0 && <p className="fb-db-banner-since">{t('database.downFor', { time: duration(downFor, i18n.language) })}</p>}
      </div>
    </div>
  )
}
