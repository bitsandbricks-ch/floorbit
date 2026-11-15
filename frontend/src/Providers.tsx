import { useMemo, type ReactNode } from 'react'
import { MantineProvider, Modal, mergeThemeOverrides } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useScheme } from './colorScheme'
import { cssVariablesResolver, theme } from './theme'

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  const scheme = useScheme()
  const { t } = useTranslation()
  // Mantine's close button is an icon with no name, so screen readers heard just "button" (issue #284).
  const themed = useMemo(() => mergeThemeOverrides(theme, {
    components: { Modal: Modal.extend({ defaultProps: { closeButtonProps: { 'aria-label': t('goto.close') } } }) },
  }), [t])
  return (
    <MantineProvider theme={themed} cssVariablesResolver={cssVariablesResolver} forceColorScheme={scheme}>
      <Notifications position="bottom-right" />
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MantineProvider>
  )
}
