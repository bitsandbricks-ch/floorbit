import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './app.css'
import './i18n'
import App from './App'
import { Providers } from './Providers'
import { queryClient } from './queryClient'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Providers>
  </StrictMode>,
)
