import { Button, CloseButton, Group, Menu, TextInput } from '@mantine/core'
import { IconCheck, IconChevronDown, IconSearch } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { useFilters } from './useFilters'

export interface FilterOption { value: string; label: string; count?: number }
export interface FilterDef { id: string; label: string; options: FilterOption[] }

/** One filter bar for lists and tables (#1020): search on the left, a chip per filter that opens its
 *  choices with counts, and Clear. The state lives in the address through ``useFilters``. */
export function FilterBar<K extends string>({ filters, state, searchLabel }: {
  filters: (FilterDef & { id: K })[]; state: ReturnType<typeof useFilters<K>>; searchLabel?: string
}) {
  const { t } = useTranslation()
  return (
    <Group gap="xs" wrap="wrap" className="fb-filterbar" role="search">
      {searchLabel && (
        <TextInput leftSection={<IconSearch size={16} />} placeholder={searchLabel} aria-label={searchLabel}
          value={state.search} onChange={(e) => state.setSearch(e.currentTarget.value)} style={{ flex: '1 1 220px', maxWidth: 360 }}
          rightSection={state.search ? <CloseButton size="sm" aria-label={t('filters.clearSearch')} onClick={() => state.setSearch('')} /> : null} />
      )}
      {filters.map((f) => {
        const value = state.values[f.id]
        const current = f.options.find((o) => o.value === value) ?? f.options[0]
        const active = value !== state.defaults[f.id]
        return (
          <Menu key={f.id} position="bottom-start">
            <Menu.Target>
              <Button variant={active ? 'light' : 'default'} color={active ? 'bit' : undefined} rightSection={<IconChevronDown size={14} />}
                aria-label={`${f.label}: ${current.label}`}>
                <span className="fb-filterbar-key">{f.label}:</span>&nbsp;{current.label}
                {current.count != null && <span className="fb-filterbar-count">{current.count}</span>}
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              {f.options.map((o) => (
                <Menu.Item key={o.value} onClick={() => state.set(f.id, o.value)}
                  leftSection={o.value === value ? <IconCheck size={14} /> : <span style={{ width: 14 }} />}
                  rightSection={o.count != null ? <span className="fb-filterbar-count">{o.count}</span> : null}>
                  {o.label}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        )
      })}
      {state.changed && <Button variant="subtle" color="gray" onClick={state.clear}>{t('filters.clear')}</Button>}
    </Group>
  )
}
