import { fireEvent, screen, within } from '@testing-library/react'

// The menu fades in, and jsdom never finishes the transition: its items count as hidden.
const items = { hidden: true } as const

/** Opens a problem row's "More actions" menu (issue #1415) and picks one of its items. */
export async function rowAction(row: HTMLElement, name: string) {
  fireEvent.click(within(row).getByRole('button', { name: 'More actions' }))
  fireEvent.click(await screen.findByRole('menuitem', { name, ...items }))
}

/** The items a row's "More actions" menu has, or none when it has no menu. */
export async function rowActions(row: HTMLElement): Promise<string[]> {
  const more = within(row).queryByRole('button', { name: 'More actions' })
  if (!more) return []
  fireEvent.click(more)
  const names = (await screen.findAllByRole('menuitem', items)).map((m) => m.textContent ?? '')
  fireEvent.click(more)
  return names
}
