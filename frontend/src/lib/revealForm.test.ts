import { describe, expect, it, vi } from 'vitest'
import { revealForm } from './revealForm'

describe('revealForm', () => {
  it('scrolls the form into view and focuses its first field', () => {
    const form = document.createElement('div')
    form.innerHTML = '<input type="hidden"><input disabled><input id="first"><textarea></textarea>'
    document.body.append(form)
    form.scrollIntoView = vi.fn()
    revealForm(form)
    expect(form.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: 'nearest' }))
    expect(document.activeElement?.id).toBe('first')
    form.remove()
  })

  it('does nothing without an element', () => {
    expect(() => revealForm(null)).not.toThrow()
  })
})
