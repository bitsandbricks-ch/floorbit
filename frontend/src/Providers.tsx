import type { ReactNode } from 'react'
import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useScheme } from './colorScheme'
import { cssVariablesResolver, theme } from './theme'

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  const scheme = useScheme()
  return (
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} forceColorScheme={scheme}>
      <Notifications position="bottom-right" />
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MantineProvider>
  )
}
