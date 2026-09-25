import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import './index.css'
import App from './App.jsx'
import { AppProvider } from './context/AppContext.jsx'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import api from './services/api'
import { IS_DEMO } from './demo/mode'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
if (!PUBLISHABLE_KEY) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY. Run `clerk env pull` in frontend/')
}

const app = (
  <AppProvider>
    <TooltipProvider>
      <App />
    </TooltipProvider>
    <Toaster />
  </AppProvider>
)

const ready = IS_DEMO ? import('./demo/install.js').then(m => m.installDemo(api)) : Promise.resolve()

ready.then(() => createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/* The demo never loads Clerk: there is no sign-in, and the snapshot answers every request. */}
    {IS_DEMO ? app : <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">{app}</ClerkProvider>}
  </StrictMode>,
))
