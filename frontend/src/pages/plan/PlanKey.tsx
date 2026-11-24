import { UnstyledButton } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconChevronDown, IconChevronUp } from '@tabler/icons-react'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

/** The legend floats over the plan's bottom-left corner, like a map's key, and folds away. */
export function PlanKey({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const phone = useMediaQuery('(max-width: 48em)')
  const [open, setOpen] = useState<boolean | null>(null)
  const shown = open ?? !phone
  return (
    <div className={shown ? 'fb-plan-key open' : 'fb-plan-key'} role="region" aria-label={t('plan.legend')}>
      <UnstyledButton className="fb-plan-key-head" aria-expanded={shown} onClick={() => setOpen(!shown)}>
        {shown ? <IconChevronDown size={14} aria-hidden="true" /> : <IconChevronUp size={14} aria-hidden="true" />}
        {t('plan.legend')}
      </UnstyledButton>
      {shown && <div className="fb-plan-key-body">{children}</div>}
    </div>
  )
}
