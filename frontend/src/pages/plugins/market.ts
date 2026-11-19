import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import type { MarketCatalog } from './Marketplace'

export const MARKET_KEY = ['marketplace'] as const

/** The signed plugin index with what is installed (GET /api/settings/marketplace). */
export function useMarketplace(enabled = true) {
  return useQuery({ queryKey: MARKET_KEY, queryFn: () => get<MarketCatalog>('/api/settings/marketplace'), enabled })
}
