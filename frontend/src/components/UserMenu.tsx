import { ActionIcon, Button, Menu, Tooltip } from '@mantine/core'
import { IconLanguage, IconLogout, IconMoon, IconSun, IconUser } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useMe } from '@/api/queries'
import { toggleScheme, useScheme } from '@/colorScheme'
import { LANGUAGES, setLang, type Lang } from '@/i18n'

function signOut() {
  // A plain form post: /logout clears the session and redirects to the sign-in page.
  const form = document.createElement('form')
  form.method = 'post'
  form.action = '/logout'
  document.body.append(form)
  form.submit()
}

export function ThemeToggle() {
  const { t } = useTranslation()
  const scheme = useScheme()
  const toggle = toggleScheme()
  if (!toggle) return null
  const label = scheme === 'light' ? t('common.themeDark') : t('common.themeLight')
  return (
    <Tooltip label={label}>
      <ActionIcon variant="subtle" color="gray" size="lg" aria-label={label} onClick={toggle}>
        {scheme === 'light' ? <IconMoon size={18} /> : <IconSun size={18} />}
      </ActionIcon>
    </Tooltip>
  )
}

export function UserMenu() {
  const { t, i18n } = useTranslation()
  const me = useMe().data
  const user = me?.user
  return (
    <Menu position="bottom-end" width={220}>
      <Menu.Target>
        <Button variant="subtle" color="gray" leftSection={<IconUser size={16} />} aria-label={user ? t('common.signedInAs', { username: user.username }) : t('common.language')}>
          {user?.display_name || user?.username || <IconLanguage size={16} />}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        {user && <Menu.Label>{t('common.signedInAs', { username: user.username })}</Menu.Label>}
        <Menu.Label>{t('common.language')}</Menu.Label>
        {LANGUAGES.map((l) => (
          <Menu.Item
            key={l.code}
            onClick={() => setLang(l.code as Lang)}
            fw={i18n.language === l.code ? 700 : undefined}
            aria-current={i18n.language === l.code ? 'true' : undefined}
            lang={l.code}
          >
            {l.label}
          </Menu.Item>
        ))}
        {me?.enabled && user && (
          <>
            <Menu.Divider />
            <Menu.Item leftSection={<IconLogout size={16} />} onClick={signOut}>
              {t('common.signOut')}
            </Menu.Item>
          </>
        )}
      </Menu.Dropdown>
    </Menu>
  )
}
