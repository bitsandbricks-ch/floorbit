import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api/client'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: true,
      // A refusal (401, 403, 404) won't change by asking again.
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
})
