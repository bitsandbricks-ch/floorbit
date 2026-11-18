import type { TFunction } from 'i18next'

/** A built-in plugin's name in the reader's language (plugins.names.<id>): the descriptive ones
 *  ("Traffic from the hall") get German, product names and Marketplace plugins keep their own. */
export function pluginName(t: TFunction, id: string | null | undefined, name: string): string {
  return id ? t(`plugins.names.${id}`, { defaultValue: name }) : name
}
