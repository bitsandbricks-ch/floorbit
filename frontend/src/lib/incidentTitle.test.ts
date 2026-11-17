import { afterEach, describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { incidentTitle, powerNote } from './incidentTitle'

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

  it('shows a power alert\'s incident in the reader\'s language, with its values', async () => {
    await i18n.changeLanguage('de-CH')
    expect(incidentTitle('Circuit C row 2 at 98.8 % of 16 A', i18n.t)).toBe('Stromkreis C row 2 bei 98.8 % von 16 A')   // Swiss numbers keep the point
    expect(incidentTitle('Breaker tripped: PDU 3', i18n.t)).toBe('Sicherung ausgelöst: PDU 3')
    await i18n.changeLanguage('en')
    expect(incidentTitle('Circuit C row 2 at 98.8 % of 16 A', i18n.t)).toBe('Circuit C row 2 at 98.8 % of 16 A')
  })

  it('shows the note Floorbit writes on a power incident in the reader\'s language', async () => {
    const note = 'Board DB-2, phase L3. Feeds 12 seats (C-13 to C-24) and switches sw-c-01, sw-c-02.'
    await i18n.changeLanguage('de-CH')
    expect(powerNote(note, i18n.t)).toBe('Verteiler DB-2, Phase L3. Speist 12 Plätze (C-13 bis C-24) und Switches sw-c-01, sw-c-02.')
    expect(powerNote('Board DB-2, phase L1. Feeds seat A-1.', i18n.t)).toBe('Verteiler DB-2, Phase L1. Speist Platz A-1.')
    expect(powerNote('Board DB-2, phase L1.', i18n.t)).toBe('Verteiler DB-2, Phase L1.')
    expect(powerNote('Swapped the strip', i18n.t)).toBe('Swapped the strip')
    await i18n.changeLanguage('en')
    expect(powerNote(note, i18n.t)).toBe(note)
  })
})
