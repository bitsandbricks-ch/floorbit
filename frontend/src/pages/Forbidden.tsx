import { Alert, Button, Stack, Text, Title } from '@mantine/core'
import { IconLock } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { PublicPage } from '@/components/PublicPage'
import { signOut } from '@/components/signOut'
import type { ForbiddenPage } from '@/lib/serverPage'
import { readBoot } from '@/nav/boot'

/** What a signed-in person sees on a page their role may not open (auth._forbidden): which
 *  permission it needs, who they are signed in as, and the two ways on. */
export default function Forbidden({ page }: { page: ForbiddenPage }) {
  const { t } = useTranslation()
  const { user } = readBoot()
  const permission = t(`teams.permission.${page.permission.replace(/\./g, '_')}`, { defaultValue: page.permission })
  return (
    <PublicPage title={t('forbidden.title')}>
      <Stack gap="md">
        <Title order={1} size="h2">{t('forbidden.title')}</Title>
        <Alert color="orange" icon={<IconLock size={18} />} title={t('forbidden.needs')}>{permission}</Alert>
        {user && <Text c="dimmed">{t('forbidden.signedInAs', { name: user.name || user.username, role: page.role })}</Text>}
        <Text c="dimmed" size="sm">{t('forbidden.ask')}</Text>
        <Button component="a" href="/">{t('common.backToPlan')}</Button>
        <Button variant="default" onClick={signOut}>{t('forbidden.switch')}</Button>
      </Stack>
    </PublicPage>
  )
}
