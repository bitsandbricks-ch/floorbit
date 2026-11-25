import { Button } from '@mantine/core'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/** How many of ``count`` lines to show: the first ``first``, until "Show all" opens the rest in
 *  place. Long text never sits in a scroll box of its own inside the page (#935): the page scrolls. */
export function useMoreLines(count: number, first: number): { limit: number; more: ReactNode } {
  const { t } = useTranslation()
  const [all, setAll] = useState(false)
  const limit = all ? count : Math.min(count, first)
  const more = limit < count
    ? <Button variant="subtle" size="xs" px={0} onClick={() => setAll(true)}>{t('moreLines.showAll', { count, hidden: count - limit })}</Button>
    : null
  return { limit, more }
}
