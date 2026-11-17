import { Button, ColorInput, Group } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

// Picks that read on the light and the dark plan alike.
const TINTS = ['#2f9e44', '#1098ad', '#1c7ed6', '#7048e8', '#ae3ec9', '#f08c00', '#e8590c', '#e03131', '#868e96']
const HEX = /^#[0-9a-f]{6}$/i

/** A mark's own colour (``tint``): a picker with swatches, or the theme's colour, which follows
 *  light and dark. ``value`` null is the theme's; with ``mixed`` the selection's colours differ. */
export function TintField({ value, mixed = false, onChange }: { value: string | null; mixed?: boolean; onChange: (tint: string | null) => void }) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(value ?? '')
  const commit = (v: string) => {
    const next = v.trim() ? v.trim().toLowerCase() : null
    if (next && !HEX.test(next)) { setDraft(value ?? ''); return }
    if (next !== value) onChange(next)
  }
  return (
    <div>
      <ColorInput label={t('plan.edit.tint.label')} format="hex" swatches={TINTS} swatchesPerRow={9} value={draft}
        placeholder={t(mixed ? 'plan.edit.mixed' : 'plan.edit.tint.theme')} withEyeDropper={false} closeOnColorSwatchClick
        onChange={setDraft} onChangeEnd={commit} onBlur={() => commit(draft)} onKeyDown={(e) => { if (e.key === 'Enter') commit(draft) }} />
      {value && (
        <Group justify="flex-end" mt={4}>
          <Button size="compact-xs" variant="subtle" onClick={() => { setDraft(''); onChange(null) }}>{t('plan.edit.tint.reset')}</Button>
        </Group>
      )}
    </div>
  )
}
