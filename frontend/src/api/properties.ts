import { useQuery } from '@tanstack/react-query'
import { get } from './client'

/** A known inventory property and the kind of value it takes (floorbit/property_catalog.py, #879). */
export type PropertyType = 'text' | 'number' | 'bool' | 'ip' | 'url' | 'choice' | 'list'

export interface PropertyDef {
  key: string
  label: string
  type: PropertyType
  unit: string
  choices: string[]
  /** Device roles it is for; empty: any. */
  roles: string[]
  hint: string
  builtin: boolean
}

export interface PropertyCatalog { properties: PropertyDef[]; types: PropertyType[] }

// Under ['inventory'], so whatever refreshes the inventory refreshes this too.
export const propertiesKey = ['inventory', 'properties'] as const

export function usePropertyCatalog() {
  return useQuery({ queryKey: propertiesKey, queryFn: () => get<PropertyCatalog>('/api/inventory/properties'), staleTime: 60_000 })
}
