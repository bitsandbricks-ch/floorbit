// The sidebar on the pages Flask still draws itself (floor plan, Settings, users, audit log):
// templates/_nav.html leaves an empty #fb-nav and loads this, a second entry of the Vite build.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import { ServerNav } from './ServerNav'

const slot = document.getElementById('fb-nav')
if (slot) {
  slot.textContent = ''
  createRoot(slot).render(<StrictMode><ServerNav /></StrictMode>)
}
