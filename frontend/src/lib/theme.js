import { useSyncExternalStore } from 'react'

// Light/dark state lives on <html class="dark">, set before first paint by index.html.
// A tiny external store so the toggle and the toaster stay in sync.
const listeners = new Set()
const emit = () => listeners.forEach(l => l())
const root = () => document.documentElement
const current = () => (root().classList.contains('dark') ? 'dark' : 'light')

function saved() {
  try { return localStorage.getItem('theme') } catch { return null }
}

export function setTheme(theme) {
  root().classList.toggle('dark', theme === 'dark')
  try { localStorage.setItem('theme', theme) } catch { /* private mode: still switches for this visit */ }
  emit()
}

// Follow the OS setting until the user picks a mode with the toggle.
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
  if (saved()) return
  root().classList.toggle('dark', e.matches)
  emit()
})

export function useTheme() {
  return useSyncExternalStore(cb => { listeners.add(cb); return () => listeners.delete(cb) }, current)
}
