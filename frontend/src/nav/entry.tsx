// The sidebar on the pages Flask still draws itself (floor plan, Settings, users, audit log):
// templates/_nav.html draws its markup into #fb-nav for the first paint (floorbit/nav.py, from
// the build's nav-shell.json) and loads this, a second entry of the Vite build, to take it over.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import { ServerNav } from './ServerNav'

const slot = document.getElementById('fb-nav')
if (slot) {
  // No clearing first: React swaps the server's markup for its own in one commit, so no frame
  // shows the slot empty.
  createRoot(slot).render(<StrictMode><ServerNav /></StrictMode>)
}
