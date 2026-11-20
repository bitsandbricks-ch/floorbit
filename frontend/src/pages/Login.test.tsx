import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LoginOptions } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Login from './Login'

const options = (over: Partial<LoginOptions> = {}): LoginOptions => ({
  enabled: true, password_login: true, providers: [], no_users: false, checkin_url: null, next: '/inventory',
  error: null, username: '', ...over,
})
const OPTIONS = 'GET /api/auth/login-options?next=%2Finventory'

beforeEach(() => window.history.pushState({}, '', '/login?next=/inventory'))
afterEach(() => { vi.unstubAllGlobals(); window.history.pushState({}, '', '/') })

describe('Login', () => {
  it('signs in with the password and says so when it is wrong', async () => {
    const fake = fakeFetch({
      [OPTIONS]: options(),
      'POST /api/auth/login': () => ({ status: 401, body: { error: 'Wrong username or password.' } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Login />, '/login?next=/inventory')
    fireEvent.change(await screen.findByLabelText(/Username/), { target: { value: ' kim ' } })
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'not-the-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password.')
    expect(fake.calls.find((c) => c.method === 'POST')?.body)
      .toEqual({ username: 'kim', password: 'not-the-password', next: '/inventory' })
    await waitFor(() => expect(screen.getByLabelText(/Password/)).toHaveValue(''))
  })

  it('shows the last error, the providers and the check-in link', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      [OPTIONS]: options({ error: 'The sign-in link expired. Please try again.', username: 'kim', checkin_url: '/checkin',
        providers: [{ id: 'discord', label: 'Discord', url: '/auth/discord/start?next=%2Finventory' }] }),
    }).fn)
    renderWithApp(<Login />, '/login?next=/inventory')
    expect(await screen.findByRole('alert')).toHaveTextContent('The sign-in link expired.')
    expect(screen.getByLabelText(/Username/)).toHaveValue('kim')
    expect(screen.getByRole('link', { name: 'Sign in with Discord' })).toHaveAttribute('href', '/auth/discord/start?next=%2Finventory')
    expect(screen.getByRole('link', { name: 'Check in to your seat' })).toHaveAttribute('href', '/checkin')
    expect(screen.getByRole('heading', { name: 'Crew sign-in' })).toBeInTheDocument()
  })

  it('explains how to make the first account', async () => {
    vi.stubGlobal('fetch', fakeFetch({ [OPTIONS]: options({ no_users: true }) }).fn)
    renderWithApp(<Login />, '/login?next=/inventory')
    expect(await screen.findByRole('link', { name: 'Set up Floorbit' })).toHaveAttribute('href', '/setup')
    expect(screen.getByText(/flask --app app users add/)).toHaveTextContent('flask --app app users add <name>')
  })

  it('says the database is away, keeps the form greyed out, and opens it once the database is back', async () => {
    let down = true
    vi.stubGlobal('fetch', fakeFetch({
      [OPTIONS]: () => (down
        ? { status: 503, body: { code: 'database_unavailable', error: 'The database is away' } }
        : { body: options() }),
    }).fn)
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderWithApp(<Login />, '/login?next=/inventory')
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
    expect(screen.getByLabelText(/Password/)).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
    down = false
    await vi.advanceTimersByTimeAsync(10_100)
    await waitFor(() => expect(screen.getByLabelText(/Password/)).toBeEnabled())
    vi.useRealTimers()
  })

  it('shows the claim beside the form and the crew title only while check-in is open', async () => {
    vi.stubGlobal('fetch', fakeFetch({ [OPTIONS]: options() }).fn)
    renderWithApp(<Login />, '/login?next=/inventory')
    expect(await screen.findByRole('heading', { name: 'Sign in', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Which switch, which port, which seat.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Check in to your seat' })).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeEnabled()
  })
})
