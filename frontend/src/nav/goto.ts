export const GOTO_EVENT = 'floorbit:goto'

/** Opens "Go to" from anywhere on a React page (the phone header's search button). */
export function openGoTo() {
  window.dispatchEvent(new Event(GOTO_EVENT))
}
