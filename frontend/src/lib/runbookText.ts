import type { TFunction } from 'i18next'

type Book = { id: string; title: string; body?: string; starter?: boolean }

/** The starter runbooks (floorbit/runbooks.py, STARTERS) in the reader's language, until the crew
 *  edits one: then it is theirs and shows as they wrote it. */
export function runbookText<B extends Book>(book: B, t: TFunction): B {
  const n = book.starter ? /^starter-(\d+)$/.exec(book.id)?.[1] : undefined
  if (!n) return book
  const title = t(`runbooks.starters.${n}.title`, { defaultValue: book.title })
  const body = book.body === undefined ? undefined : t(`runbooks.starters.${n}.body`, { defaultValue: book.body })
  return { ...book, title, ...(body === undefined ? {} : { body }) }
}
