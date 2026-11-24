import { type MutableRefObject, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { type Raw, rawOf } from './clipboard'
import type { ItemRef } from './geometry'
import type { Step } from './history'

const PATH = '/api/seat-blocks'
const url = (id: string) => `${PATH}/${encodeURIComponent(id)}`

/** Merging the selected seat blocks into one and splitting one at a row (#1208), each one step to
 *  undo. The server does the geometry (floorbit/block_merge.py, floorbit/block_split.py). */
export function useBlockJoin({ hall, push, refresh, fail, select, idOf, alias }: {
  hall: string
  push: (step: Step) => void
  refresh: () => Promise<unknown>
  fail: (err: unknown) => void
  select: (refs: ItemRef[]) => void
  idOf: (ref: ItemRef) => string
  alias: MutableRefObject<Map<string, string>>
}) {
  const { t } = useTranslation()
  const ref = (id: string): ItemRef => ({ kind: 'block', id })
  // The blocks as the server keeps them now, to put back on undo.
  const saved = useCallback(async (ids: string[]) => {
    const all = await get<Record<string, unknown>[]>(`${PATH}?hall=${encodeURIComponent(hall)}`)
    return ids.map((id) => {
      const raw = all.find((b) => b.id === id)
      if (!raw) throw new Error(t('blockJoin.gone'))
      return rawOf('block', raw)
    })
  }, [hall, t])
  // A removed block comes back with a new id; later steps still name the old one.
  const restore = useCallback(async (id: string, raw: Raw) => {
    const made = await post<{ id: string }>(PATH, { ...raw.body, hall_id: hall })
    alias.current.set(`block:${id}`, made.id)
  }, [alias, hall])

  const merge = useCallback(async (ids: string[]) => {
    try {
      const before = await saved(ids)
      const run = () => post<{ block: { id: string }; removed: string[] }>(`${PATH}/merge`, { ids: ids.map((id) => idOf(ref(id))) })
      const done = await run()
      // The server keeps the top or left block, whichever was picked first.
      const kept = ids.find((id) => idOf(ref(id)) === done.block.id) ?? done.block.id
      push({
        label: t('blockJoin.stepMerge', { count: ids.length }),
        undo: async () => {
          await put(url(idOf(ref(kept))), before[ids.indexOf(kept)].body)
          for (const [i, id] of ids.entries()) if (id !== kept) await restore(id, before[i])
          await refresh()
        },
        redo: () => run().then(refresh),
      })
      select([ref(done.block.id)])
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [saved, idOf, push, t, restore, refresh, select, fail])

  const split = useCallback(async (id: string, at: number) => {
    try {
      const [before] = await saved([id])
      const run = () => post<{ block: { id: string }; new: { id: string } }>(`${url(idOf(ref(id)))}/split`, { at })
      const done = await run()
      const made = done.new.id
      push({
        label: t('blockJoin.stepSplit'),
        undo: async () => {
          await del(url(idOf(ref(made))))
          await put(url(idOf(ref(id))), before.body)
          await refresh()
        },
        redo: async () => {
          const again = await run()
          alias.current.set(`block:${idOf(ref(made))}`, again.new.id)
          await refresh()
        },
      })
      select([ref(done.block.id), ref(made)])
    } catch (err) {
      fail(err)
    }
    await refresh()
  }, [saved, idOf, push, t, alias, refresh, select, fail])

  return { merge, split }
}
