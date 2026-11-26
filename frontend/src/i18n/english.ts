// The English texts the app shell's pages need beyond englishCore.ts: one file, fetched with the shell.
type Texts = Record<string, unknown>
export const files = import.meta.glob<Texts>([
  './en/*.json',
  '!./en/checkin.json',
  '!./en/common.json',
  '!./en/database.json',
  '!./en/goto.json',
  '!./en/login.json',
  '!./en/publicPages.json',
  '!./en/publicStatus.json',
  '!./en/seatHelp.json',
  '!./en/ui.json',
  '!./en/version.json',
], { eager: true, import: 'default' })
