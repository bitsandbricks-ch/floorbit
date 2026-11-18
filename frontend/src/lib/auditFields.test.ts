import i18n from 'i18next'
import { afterEach, describe, expect, it } from 'vitest'
import '@/i18n'
import { fieldsText } from './auditFields'

afterEach(() => { void i18n.changeLanguage('en') })

describe('fieldsText', () => {
  it('names changed settings by their label, in the reader\'s language', async () => {
    expect(fieldsText(i18n.t, 'settings', ['public.stats_wall', 'no.such_key'])).toBe('Stats wall, no.such_key')
    expect(fieldsText(i18n.t, 'incidents', ['status'])).toBe('status')
    expect(fieldsText(i18n.t, 'incidents', ['slow'])).toBe('Slow or dropping connection')
    await i18n.changeLanguage('de-CH')
    expect(fieldsText(i18n.t, 'settings', ['public.stats_wall'])).not.toBe('public.stats_wall')
  })
})
