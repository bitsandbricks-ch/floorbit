import { Menu, UnstyledButton } from '@mantine/core'
import { IconBuildingCommunity, IconCheck, IconDots, IconLanguage, IconLogout, IconMoon, IconSelector, IconSun, type Icon } from '@tabler/icons-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toggleScheme, useScheme } from '@/colorScheme'
import { LANGUAGES, setLang, type Lang } from '@/i18n/lang'
import { fetchOtherTenants, switchTenant, type NavBoot, type OtherTenant } from './boot'

/** An extra entry in the account menu (notifications and the crew notice). */
export interface MenuAction { id: string; label: string; icon: Icon; run: () => void }

function initials(name: string) {
  return name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?'
}

/** The event's logo, the event's name, or Floorbit's lockup (a mark alone when folded). */
export function Brand({ boot, rail }: { boot: NavBoot; rail: boolean }) {
  const { t } = useTranslation()
  let body: ReactNode
  if (boot.brand.logo) body = <img className="fb-nav-logo" src={boot.brand.logo} alt={boot.brand.name || 'Event logo'} />
  else if (rail || boot.brand.name) {
    body = (
      <span className="fb-brand">
        <span className="fb-brand-mark" role="img" aria-label="Floorbit" />
        {!rail && boot.brand.name && <span className="fb-brand-name">{boot.brand.name}</span>}
      </span>
    )
  } else body = <span className="fb-brand"><span className="fb-brand-lockup" role="img" aria-label="Floorbit" /></span>
  // The floor plan is a page Flask draws, so a plain link.
  return <a href="/" className="fb-nav-brand" title={t('nav.home')}>{body}</a>
}

/** The tenant switcher: only there when this person can reach another tenant of the platform. */
export function Tenants({ boot, rail }: { boot: NavBoot; rail: boolean }) {
  const { t } = useTranslation()
  const [list, setList] = useState<OtherTenant[] | null>(null)
  const [going, setGoing] = useState<string | null>(null)
  const [error, setError] = useState('')
  const ask = !!boot.tenants && !!boot.user && !boot.user.platform

  useEffect(() => {
    if (!ask) return
    let live = true
    void fetchOtherTenants().then((found) => { if (live) setList(found) })
    return () => { live = false }
  }, [ask])

  if (!list?.length) return null
  const here = boot.brand.name || t('nav.thisTenant')
  const go = (o: OtherTenant) => {
    setGoing(o.id)
    setError('')
    switchTenant(o.id)
      .then((url) => { window.location.assign(url) })
      .catch((e: unknown) => { setGoing(null); setError(e instanceof Error ? e.message : String(e)) })
  }
  return (
    <Menu position={rail ? 'right-end' : 'top-start'} width={224} withinPortal closeOnItemClick={false}>
      <Menu.Target>
        <UnstyledButton className="fb-nav-row fb-nav-tenant" title={rail ? t('nav.switchTenant') : undefined} aria-label={rail ? t('nav.switchTenant') : undefined}>
          <IconBuildingCommunity size={18} className="fb-nav-icon" aria-hidden="true" />
          {!rail && <span className="fb-nav-text">{here}</span>}
          {!rail && <IconSelector size={14} className="fb-nav-tenant-mark" aria-hidden="true" />}
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{t('nav.switchTenant')}</Menu.Label>
        {list.map((o) => (
          <Menu.Item key={o.id} disabled={!!going} onClick={() => go(o)}
            rightSection={<span className="fb-nav-tenant-how">{going === o.id ? t('nav.switching') : o.how === 'platform' ? t('nav.asPlatform') : ''}</span>}>
            {o.name || o.id}
          </Menu.Item>
        ))}
        {error && <Menu.Label role="alert">{error}</Menu.Label>}
      </Menu.Dropdown>
    </Menu>
  )
}

/** The account menu: language, light or dark, the page's extra actions and "Sign out". */
export function Account(props: { boot: NavBoot; actions?: MenuAction[]; rail: boolean }) {
  const { t, i18n } = useTranslation()
  const scheme = useScheme()
  const toggle = toggleScheme()
  const user = props.boot.user
  const name = user ? user.name || user.username : t('nav.account')
  return (
    <Menu position={props.rail ? 'right-end' : 'top-start'} width={224} withinPortal>
      <Menu.Target>
        <UnstyledButton
          className="fb-nav-row fb-nav-me" title={props.rail ? name : undefined}
          // In the rail only the avatar shows, so the button needs a label. Expanded, the button reads
          // its name from its text, not from an aria-label that hides the name on screen.
          aria-label={props.rail ? (user ? t('common.signedInAs', { username: user.username }) : t('nav.account')) : undefined}
        >
          <span className="fb-nav-avatar" aria-hidden="true">{user ? initials(name) : <IconDots size={16} />}</span>
          {user && !props.rail && <span className="fb-sr-only">{t('common.signedInAs', { username: user.username })}</span>}
          {!props.rail && <span className="fb-nav-text" aria-hidden={user ? true : undefined}>{name}</span>}
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        {user && <Menu.Label>{t('common.signedInAs', { username: user.username })}</Menu.Label>}
        {user?.platform && <Menu.Label>{t('nav.platformVisit')}</Menu.Label>}
        <Menu.Label><IconLanguage size={14} aria-hidden="true" /> {t('common.language')}</Menu.Label>
        {LANGUAGES.map((l) => (
          <Menu.Item key={l.code} aria-current={i18n.language === l.code ? 'true' : undefined} lang={l.code}
            rightSection={i18n.language === l.code ? <IconCheck size={14} aria-hidden="true" /> : null} onClick={() => setLang(l.code as Lang)}>
            {l.label}
          </Menu.Item>
        ))}
        {toggle && (
          <>
            <Menu.Divider />
            <Menu.Item leftSection={scheme === 'light' ? <IconMoon size={16} aria-hidden="true" /> : <IconSun size={16} aria-hidden="true" />} onClick={toggle}>
              {scheme === 'light' ? t('common.themeDark') : t('common.themeLight')}
            </Menu.Item>
          </>
        )}
        {!!props.actions?.length && <Menu.Divider />}
        {props.actions?.map((a) => (
          <Menu.Item key={a.id} leftSection={<a.icon size={16} aria-hidden="true" />} onClick={a.run}>{a.label}</Menu.Item>
        ))}
        {props.boot.signOut && user && (
          <>
            <Menu.Divider />
            <form method="post" action="/logout">
              <Menu.Item component="button" type="submit" leftSection={<IconLogout size={16} aria-hidden="true" />}>{t('common.signOut')}</Menu.Item>
            </form>
          </>
        )}
      </Menu.Dropdown>
    </Menu>
  )
}
