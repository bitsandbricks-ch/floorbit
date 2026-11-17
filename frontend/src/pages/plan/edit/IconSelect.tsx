import { Group, Select } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { CustomIconGlyph } from '../../inventory/icons'
import { useCustomIcons } from '../../inventory/scope'

/** The icon of a plan icon: a built-in one (floorbit/plan_icons.py) or one uploaded to the icon
 *  library on the Inventory page (floorbit/icon_library.py), the same ones devices and groups use. */
export function PlanIconSelect({ value, onChange, autoFocus }: { value: string | null; onChange: (icon: string | null) => void; autoFocus?: boolean }) {
  const { t } = useTranslation()
  const builtIn = useQuery({ queryKey: qk.planIcons, queryFn: () => get<{ icons: Record<string, string[]> }>('/api/plan-marks?hall=-'), staleTime: Infinity })
  const uploaded = useCustomIcons().data?.icons ?? []
  const paths = builtIn.data?.icons ?? {}
  const names = Object.keys(paths)
  const data = [
    { group: t('plan.edit.mark.builtIn'), items: names.map((n) => ({ value: n, label: t(`plan.edit.icons.${n}`, { defaultValue: n.replace(/[-_]/g, ' ') }) })) },
    ...(uploaded.length ? [{ group: t('plan.edit.mark.uploaded'), items: uploaded.map((u) => ({ value: u.id, label: u.name })) }] : []),
  ]
  const glyph = (icon: string) => {
    const up = uploaded.find((u) => u.id === icon)
    return up ? <CustomIconGlyph url={up.url} size={18} /> : <IconGlyph paths={paths[icon] ?? []} />
  }
  return (
    <Select label={t('plan.edit.mark.icon')} searchable value={value} onChange={onChange} data-autofocus={autoFocus || undefined}
      nothingFoundMessage={t('plan.edit.mark.none')} data={data} allowDeselect={false}
      leftSection={value ? glyph(value) : undefined}
      renderOption={({ option }) => <Group gap="xs" wrap="nowrap">{glyph(option.value)}{option.label}</Group>} />
  )
}

function IconGlyph({ paths }: { paths: string[] }) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}
