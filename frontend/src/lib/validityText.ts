import type { i18n as I18n } from 'i18next'

type Field = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement

/** The browser's own "Please fill out this field" bubble speaks the browser's language and says
 *  little; this gives it the app's language and a clearer text. The check itself stays the
 *  browser's: only the message changes, and typing clears it so the field is checked afresh. */
export function validityMessage(el: Field, t: I18n['t']): string {
  const v = el.validity
  if (v.valueMissing) return t('ui.validity.required')
  if (v.typeMismatch && el.type === 'email') return t('ui.validity.email')
  if (v.typeMismatch && el.type === 'url') return t('ui.validity.url')
  if (v.tooShort) return t('ui.validity.tooShort', { count: (el as HTMLInputElement).minLength })
  if (v.rangeUnderflow) return t('ui.validity.min', { min: (el as HTMLInputElement).min })
  if (v.rangeOverflow) return t('ui.validity.max', { max: (el as HTMLInputElement).max })
  return ''
}

const isField = (n: EventTarget | null): n is Field =>
  n instanceof HTMLInputElement || n instanceof HTMLTextAreaElement || n instanceof HTMLSelectElement

export function installValidityText(i18n: I18n, root: Document = document) {
  root.addEventListener('invalid', (e) => {
    if (!isField(e.target)) return
    e.target.setCustomValidity('')
    e.target.setCustomValidity(validityMessage(e.target, i18n.t.bind(i18n)))
  }, true)
  const clear = (e: Event) => { if (isField(e.target)) e.target.setCustomValidity('') }
  root.addEventListener('input', clear, true)
  root.addEventListener('change', clear, true)
}
