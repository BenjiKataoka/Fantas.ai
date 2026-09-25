// Decided once, at page load: /demo and anything under it runs on the recorded snapshot.
export const IS_DEMO = typeof window !== 'undefined' && /^\/demo(\/|$)/.test(window.location.pathname)
