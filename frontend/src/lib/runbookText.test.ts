import { describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { runbookText } from './runbookText'

describe('runbookText', () => {
  it('shows a starter in German and leaves the crew\'s own runbooks as written', async () => {
    await i18n.changeLanguage('de-CH')
    try {
      const t = i18n.getFixedT('de-CH')
      const starter = runbookText({ id: 'starter-1', title: 'No internet at the seat', body: 'x', starter: true }, t)
      expect(starter.title).toBe('Kein Internet am Platz')
      expect(starter.body).not.toBe('x')
      const own = { id: 'abc', title: 'No internet at the seat', body: 'Our steps', starter: false }
      expect(runbookText(own, t)).toEqual(own)
      const edited = { id: 'starter-1', title: 'Ours', body: 'Ours', starter: false }
      expect(runbookText(edited, t)).toEqual(edited)
    } finally {
      await i18n.changeLanguage('en')
    }
  })
})
