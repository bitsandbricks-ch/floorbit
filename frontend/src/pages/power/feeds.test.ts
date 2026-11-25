import { afterEach, describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { feedsText, feedText } from './feeds'

// Feeds read as the plan names rows, in the reader's language (issue #1427).
describe('feedText', () => {
  afterEach(async () => { await i18n.changeLanguage('en') })

  it('names a block\'s rows the way the plan does', () => {
    expect(feedText(i18n.t, { block: 'B', rows: ['2'], by_rows: false })).toBe('B · row 2')
    expect(feedText(i18n.t, { block: 'A', rows: ['1', '2'], by_rows: false })).toBe('A · rows 1, 2')
    expect(feedText(i18n.t, { block: 'A', rows: [], by_rows: false })).toBe('Block A')
    expect(feedText(i18n.t, { block: 'C–D', rows: ['D'], by_rows: true })).toBe('Row D')
    expect(feedText(i18n.t, { block: 'C–D', rows: [], by_rows: true })).toBe('Rows C–D')
    expect(feedText(i18n.t, { block: null, rows: [], by_rows: false })).toBe('A removed block')
    expect(feedsText(i18n.t, { feeds_parts: [{ block: 'A', rows: [], by_rows: false }, { block: 'B', rows: ['1'], by_rows: false }] }))
      .toBe('Block A; B · row 1')
  })

  it('speaks German', async () => {
    await i18n.changeLanguage('de-CH')
    expect(feedText(i18n.t, { block: 'B', rows: ['2'], by_rows: false })).toBe('B · Reihe 2')
    expect(feedText(i18n.t, { block: 'A', rows: ['1', '2'], by_rows: false })).toBe('A · Reihen 1, 2')
    expect(feedText(i18n.t, { block: 'C–D', rows: [], by_rows: true })).toBe('Reihen C–D')
  })
})
