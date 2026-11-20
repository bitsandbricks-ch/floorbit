import { Badge, type BadgeProps } from '@mantine/core'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { STATE_TONE, toneColor, type StateWord } from './stateTone'

/** A state as a small badge: one colour and one word per state on every page. ``label`` replaces the
 *  word where the page says something more exact ("3 failed"), and keeps the colour. */
export function StateBadge({ state, label, size = 'sm' }: { state: StateWord; label?: ReactNode; size?: BadgeProps['size'] }) {
  const { t } = useTranslation()
  return (
    <Badge size={size} variant="light" color={toneColor(STATE_TONE[state])} tt="none" miw="max-content" data-state={state}>
      {label ?? t(`state.${state}`)}
    </Badge>
  )
}

/** A state as the small square bit beside a name (never a round dot, see nav/nav.css). Without ``label`` it is decoration: the row's text
 *  says the state. */
export function StateBit({ state, label }: { state: StateWord; label?: string }) {
  return <span className={`fb-bit is-${STATE_TONE[state]}`} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true} />
}
