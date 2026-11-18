import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './ui.css'
import './app.css'
import i18n from './i18n'
import { installValidityText } from './lib/validityText'
import App from './App'
import { Providers } from './Providers'
import { queryClient } from './queryClient'

installValidityText(i18n)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Providers>
  </StrictMode>,
)
