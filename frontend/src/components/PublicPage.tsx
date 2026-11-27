import { Select, Stack } from '@mantine/core'
import { type ReactNode, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Attribution } from '@/components/Attribution'
import { LANGUAGES, type Lang, setLang } from '@/i18n'
import { readBrand } from '@/nav/bootData'

/** The event's logo or name, else Floorbit's: the same choice as the sidebar's brand. */
export function EventBrand() {
  const brand = readBrand()
  if (brand.logo) return <img className="fb-public-logo" src={brand.logo} alt={brand.name || 'Event logo'} />
  return (
    <span className="fb-brand fb-public-brand">
      {brand.name
        ? <><span className="fb-brand-mark" role="img" aria-label="Floorbit" /><span className="fb-brand-name">{brand.name}</span></>
        : <span className="fb-brand-lockup" role="img" aria-label="Floorbit" />}
    </span>
  )
}

/** The frame of the pages people see without an account (sign-in, seat check-in, the status page,
 *  ...): the event's brand on top, one column in the middle, the language picker and the
 *  attribution below. ``size``: ``form`` (sign-in, check-in), ``page`` for pages that read top to
 *  bottom (status, schedule), ``board`` for grids of numbers (stats wall). */
export function PublicPage({ title, children, size = 'form' }: { title: string; children: ReactNode; size?: 'form' | 'page' | 'board' }) {
  const { t, i18n } = useTranslation()
  useEffect(() => { document.title = `${title} · Floorbit` }, [title])
  return (
    <main className={size === 'form' ? 'fb-public' : `fb-public fb-public--${size}`}>
      <div className="fb-public-col">
        <div className="fb-public-head"><EventBrand /></div>
        <Stack gap="md">{children}</Stack>
        <Select mt="lg" size="xs" w={220} mx="auto" aria-label={t('login.language')} allowDeselect={false}
          data={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))} value={i18n.language}
          onChange={(v) => { if (v) setLang(v as Lang) }} />
      </div>
      <Attribution />
    </main>
  )
}
