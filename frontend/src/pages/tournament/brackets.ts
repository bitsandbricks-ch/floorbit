/** The i18n key for round r of n: the last three have names, the rest a number. */
export function roundName(r: number, count: number): string {
  const left = count - r
  return left === 1 ? 'brackets.final' : left === 2 ? 'brackets.semi' : left === 3 ? 'brackets.quarter' : 'brackets.round'
}
