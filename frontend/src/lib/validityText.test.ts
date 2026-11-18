import i18n from 'i18next'
import { beforeAll, describe, expect, it } from 'vitest'
import '@/i18n'
import { installValidityText, validityMessage } from './validityText'

describe('installValidityText', () => {
  beforeAll(() => installValidityText(i18n))

  it('says what is missing in the app language, and typing clears it', async () => {
    await i18n.changeLanguage('de-CH')
    const input = document.createElement('input')
    input.required = true
    document.body.append(input)
    expect(input.checkValidity()).toBe(false)
    expect(input.validationMessage).toBe('Bitte fülle dieses Feld aus.')
    input.value = 'x'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    expect(input.checkValidity()).toBe(true)
    input.remove()
    await i18n.changeLanguage('en')
  })

  it('names the minimum length and a wrong email address', () => {
    const t = i18n.t.bind(i18n)
    const field = (validity: Partial<ValidityState>, extra: object = {}) =>
      ({ validity, type: 'text', minLength: -1, ...extra }) as unknown as HTMLInputElement
    expect(validityMessage(field({ tooShort: true }, { minLength: 8 }), t)).toBe('Use at least 8 characters.')
    expect(validityMessage(field({ typeMismatch: true }, { type: 'email' }), t)).toBe('Enter an email address, like name@example.com.')
    expect(validityMessage(field({ patternMismatch: true }), t)).toBe('')
  })
})
