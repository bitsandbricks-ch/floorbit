import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './ui.css'
import './app.css'
import i18n, { i18nReady } from './i18n'
import { installValidityText } from './lib/validityText'
import App from './App'
import { Providers } from './Providers'
import { queryClient } from './queryClient'

installValidityText(i18n)

// German comes in its own file: wait for it (a few ms) rather than paint English first.
void i18nReady.finally(() => createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Providers>
  </StrictMode>,
))
