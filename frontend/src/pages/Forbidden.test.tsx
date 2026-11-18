import { screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it } from 'vitest'
import { readServerPage } from '@/lib/serverPage'
import { renderWithApp } from '@/test/render'
import Forbidden from './Forbidden'

function tag(id: string, data: unknown) {
  const el = document.createElement('script')
  el.type = 'application/json'
  el.id = id
  el.textContent = JSON.stringify(data)
  document.body.append(el)
}

afterEach(() => {
  document.getElementById('fb-page')?.remove()
  document.getElementById('fb-nav-data')?.remove()
  void i18n.changeLanguage('en')
})

describe('Forbidden', () => {
  it('reads what the server put into the page', () => {
    expect(readServerPage()).toBeNull()
    tag('fb-page', { kind: 'forbidden', permission: 'settings.manage', role: 'Lead' })
    expect(readServerPage()).toEqual({ kind: 'forbidden', permission: 'settings.manage', role: 'Lead' })
  })

  it('names the permission, the account and the ways on', async () => {
    tag('fb-nav-data', { pages: [], brand: { logo: null, name: null }, user: { name: 'Ana', username: 'ana' }, signOut: true, prefs: null })
    renderWithApp(<Forbidden page={{ kind: 'forbidden', permission: 'settings.manage', role: 'Lead' }} />, '/settings')
    expect(await screen.findByRole('heading', { name: 'Not allowed' })).toBeInTheDocument()
    expect(screen.getByText('Change settings, plugins and backups')).toBeInTheDocument()
    expect(screen.getByText('You are signed in as Ana (Lead).')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the floor plan' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('button', { name: 'Sign in as someone else' })).toBeInTheDocument()
    await i18n.changeLanguage('de-CH')
    expect(await screen.findByRole('heading', { name: 'Nicht erlaubt' })).toBeInTheDocument()
  })
})
