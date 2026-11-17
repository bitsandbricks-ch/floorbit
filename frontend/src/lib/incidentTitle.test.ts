import { afterEach, describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { incidentTitle } from './incidentTitle'

describe('incidentTitle', () => {
  afterEach(async () => { await i18n.changeLanguage('en') })

  it('shows a report from the seat in the reader\'s language, and anything else as written', async () => {
    await i18n.changeLanguage('de-CH')
    expect(incidentTitle('No power at the seat', i18n.t)).toBe('Kein Strom am Platz')
    expect(incidentTitle('Needs help at the seat', i18n.t)).toBe('Braucht Hilfe am Platz')
    expect(incidentTitle('Switch in row C beeps', i18n.t)).toBe('Switch in row C beeps')
    await i18n.changeLanguage('en')
    expect(incidentTitle('Slow connection', i18n.t)).toBe('Slow connection')
  })
})
