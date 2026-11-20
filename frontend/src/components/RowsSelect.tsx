import { MultiSelect, type MultiSelectProps } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EntityOption } from './EntitySelect'

type Props = Omit<MultiSelectProps, 'data' | 'value' | 'onChange'> & {
  value: string[]
  onChange: (rows: string[]) => void
}

/** The hall's rows by name, grouped by block (#1057): the crew works a row at a time, and a block
 *  can hold several rows. Picked in order: rows are walked and patched in the order picked. */
export function RowsSelect({ value, onChange, ...rest }: Props) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: qk.options('rows', ''),
    queryFn: () => get<{ options: EntityOption[] }>('/api/options/rows'),
    staleTime: 30_000,
  })
  const all = query.data?.options ?? []
  const groups = [...new Set(all.map((o) => o.group ?? ''))]
  const item = (o: EntityOption) => ({ value: o.value, label: t('ui.rowSeats', { row: o.label, count: Number(o.hint) || 0 }) })
  const data = groups.length > 1
    ? groups.map((g) => ({ group: g || t('ui.group.other'), items: all.filter((o) => (o.group ?? '') === g).map(item) }))
    : all.map(item)
  return (
    <MultiSelect searchable hidePickedOptions data={data} value={value} onChange={onChange}
      placeholder={value.length ? undefined : t('ui.pickRows')}
      nothingFoundMessage={query.isPending ? t('common.loading') : t('ui.nothingFound')} {...rest} />
  )
}
