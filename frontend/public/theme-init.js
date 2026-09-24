// Sets the theme class before first paint, so a dark-mode user never sees a white flash.
// A separate file rather than an inline <script> so the Content-Security-Policy can stay
// strict ('self' only, no hash to keep in sync with every edit). Loaded render-blocking
// from <head> in index.html, which is what makes it run before paint.
try {
  var t = localStorage.getItem('theme')
  if (t !== 'light' && t !== 'dark') t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  document.documentElement.classList.toggle('dark', t === 'dark')
} catch (e) {}
