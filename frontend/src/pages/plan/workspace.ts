import { type LayerId, type LayerState, writeLayers } from './layers'

/** The plan is one map editor: live status is always drawn, the layers say what else shows, and crew
 *  with floorplan.edit pick a tool from the rail to change the plan (``?edit=1``). There used to be
 *  modes (``?mode=live|checkin|network|edit``); old links and bookmarks still open the same view. */
const OLD_MODES: Record<string, LayerId[]> = {
  checkin: ['grid', 'marks', 'checkin'],
  network: ['grid', 'marks', 'network', 'status', 'firewalls', 'wifi'],
}

export const isEditing = (params: URLSearchParams) => params.get('edit') === '1'

/** ``params`` without the old ``mode``, carried over to what it showed; null when there is none. */
export function fromOldMode(params: URLSearchParams, state: LayerState): URLSearchParams | null {
  const mode = params.get('mode')
  if (mode === null) return null
  let next = new URLSearchParams(params)
  next.delete('mode')
  if (mode === 'edit') next.set('edit', '1')
  const layers = OLD_MODES[mode]
  if (layers && !params.has('layers')) next = writeLayers(next, { on: new Set(layers), fade: state.fade })
  if (mode === 'checkin' && !params.has('show')) next.set('show', 'checked_in')
  return next
}

/** ``params`` with the editor's tools in hand or put down. Editing has its own selection, so the
 *  seat, block and switch panels close; the list has nothing to edit, so it goes back to the map. */
export function setEditing(params: URLSearchParams, on: boolean): URLSearchParams {
  const next = new URLSearchParams(params)
  if (on) {
    next.set('edit', '1')
    for (const k of ['seat', 'block', 'switch', 'view']) next.delete(k)
  } else next.delete('edit')
  return next
}

export const kioskHref = (hall: string, params: URLSearchParams) => {
  const next = new URLSearchParams()
  next.set('screen', '1')
  if (hall) next.set('hall', hall)
  for (const k of ['layers', 'fade', 'show']) { const v = params.get(k); if (v) next.set(k, v) }
  return `/plan?${next.toString()}`
}
