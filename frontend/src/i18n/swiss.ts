// The rest of the Swiss German texts in one module, so the app fetches them as one file (see index.ts).
type Texts = Record<string, unknown>
export const files = import.meta.glob<Texts>([
  './de-CH/*.json',
  '!./de-CH/checkin.json',
  '!./de-CH/common.json',
  '!./de-CH/database.json',
  '!./de-CH/goto.json',
  '!./de-CH/login.json',
  '!./de-CH/publicPages.json',
  '!./de-CH/publicStatus.json',
  '!./de-CH/seatHelp.json',
  '!./de-CH/ui.json',
  '!./de-CH/version.json',
], { eager: true, import: 'default' })
