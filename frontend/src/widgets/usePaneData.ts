import type { UseQueryResult } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { type Shaping, shapeData } from './kinds/combine'

/** A pane's sources, merged, grouped and calculated (issue #959). It waits for the first source
 *  only: the others join as they arrive, and one that fails is left out. ``labels`` name the
 *  sources (the tiles' names), since a widget's own label may be empty. */
export function usePaneData(results: UseQueryResult<Widget>[], how: Shaping, labels: string[] = []) {
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
  return {
    data: shaped?.widget,
    dropped: shaped?.dropped ?? [],
    error: first?.error ?? null,
    isPending: first?.isPending ?? true,
  }
}
