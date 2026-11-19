import { Anchor } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { HintLink } from './model'

/** "How to fix" next to a plugin's warning: the page that shows it, or the docs. */
export function HintAnchor({ link }: { link?: HintLink }) {
  const { t } = useTranslation()
  if (!link) return null
  const label = link.internal ? t('agents.hint.showDevices') : t('agents.hint.howToFix')
  return link.internal
    ? <Anchor component={Link} to={link.href} size="xs">{label}</Anchor>
    : <Anchor href={link.href} target="_blank" rel="noreferrer" size="xs">{label}</Anchor>
}
