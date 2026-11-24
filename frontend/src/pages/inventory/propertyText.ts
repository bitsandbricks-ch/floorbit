import type { TFunction } from 'i18next'
import type { PropertyDef } from '@/api/properties'

// Floorbit's own properties have their label and help in both languages; an admin's are as typed.
const id = (key: string) => key.replace(/\./g, '_')

export function propLabel(t: TFunction, def: PropertyDef) {
  return def.builtin ? t(`inventory.propBuiltin.${id(def.key)}.label`, { defaultValue: def.label }) : def.label
}

export function propHint(t: TFunction, def: PropertyDef) {
  return def.builtin && def.hint ? t(`inventory.propBuiltin.${id(def.key)}.hint`, { defaultValue: def.hint }) : def.hint
}
