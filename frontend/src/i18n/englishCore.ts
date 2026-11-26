// The English texts the pages outside the app shell use (sign-in, check-in, the public status and seat
// help pages): part of the first download. The rest is english.ts, fetched with the shell (issue #1293).
// The list is here and, negated, in english.ts, swissCore.ts and swiss.ts: i18n.test.ts checks they agree.
type Texts = Record<string, unknown>
export const files = import.meta.glob<Texts>([
  './en/checkin.json',
  './en/common.json',
  './en/database.json',
  './en/goto.json',
  './en/login.json',
  './en/publicPages.json',
  './en/publicStatus.json',
  './en/seatHelp.json',
  './en/ui.json',
  './en/version.json',
], { eager: true, import: 'default' })
