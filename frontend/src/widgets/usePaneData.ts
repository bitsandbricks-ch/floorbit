import type { UseQueryResult } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { type Shaping, shapeData } from './kinds/combine'
import { type Display, applyDisplay } from './kinds/display'

/** A pane's sources, merged, grouped and calculated (issue #959). It waits for the first source
 *  only: the others join as they arrive, and one that fails is left out. ``labels`` name the
 *  sources (the tiles' names), since a widget's own label may be empty. ``display`` then sets
 *  units, mappings, colour steps and which rows (issue #960). */
export function usePaneData(results: UseQueryResult<Widget>[], how: Shaping, labels: string[] = [], display?: Display) {
  const { t, i18n } = useTranslation()
  const [first] = results
  const ready = results.flatMap((r, i) => (r.data ? [{ ...r.data, label: labels[i] || r.data.label }] : []))
  const key = `${results.map((r) => r.dataUpdatedAt).join(',')}|${labels.join('\n')}`
  const shaped = useMemo(
    () => (first?.data ? shapeData(ready, how, i18n.language, {
      name: t('widgets.kind.name'), value: t('widgets.kind.value'), state: t('widgets.kind.state'), detail: t('widgets.kind.detail'),
    }, (s) => t(`widgets.state.${s}`)) : null),
    // ``key`` changes whenever any source's data or name does; ``ready`` is rebuilt every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, how.group_by, how.reduce, i18n.language, t],
  )
  const dkey = JSON.stringify(display ?? null)
  const shown = useMemo(
    () => (shaped && display ? applyDisplay(shaped.widget, display, i18n.language) : shaped?.widget),
    // ``dkey`` stands for ``display``, which is a new object every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shaped, dkey, i18n.language],
  )
  return {
    data: shown,
    dropped: shaped?.dropped ?? [],
    error: first?.error ?? null,
    isPending: first?.isPending ?? true,
  }
}
