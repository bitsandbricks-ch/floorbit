import { useCallback, useMemo, type ReactNode } from 'react'
import { Modal, mergeThemeOverrides } from '@mantine/core'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { BnbProvider } from '@bitsandbricks/ui'
import { floorbitSchemeManager, useScheme } from './colorScheme'
import { AppLink } from './nav/AppLink'
import { theme } from './theme'

const schemeManager = floorbitSchemeManager()

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  const scheme = useScheme()
  const { t, i18n } = useTranslation()
  // Mantine's close button is an icon with no name, so screen readers heard just "button" (issue #284).
  const themed = useMemo(() => mergeThemeOverrides(theme, {
    components: { Modal: Modal.extend({ defaultProps: { closeButtonProps: { 'aria-label': t('goto.close') } } }) },
  }), [t])
  // The shared components bring their own English and German; a key Floorbit has wins.
  const translate = useCallback(
    (key: string, vars?: Record<string, unknown>) => (i18n.exists(key) ? t(key, vars) : undefined),
    [t, i18n],
  )
  return (
    <BnbProvider theme={themed} locale={i18n.language.startsWith('de') ? 'de' : 'en'} translate={translate}
      link={AppLink} useSearchParams={useSearchParams} colorSchemeManager={schemeManager} defaultColorScheme={scheme}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </BnbProvider>
  )
}
