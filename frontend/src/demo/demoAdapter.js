// The demo's stand-in for the network: every request the app makes is answered from the
// recorded snapshot. Pure functions, so node can test them without a browser.

export const DEMO_WRITE_MESSAGE = 'This is a demo, so changes are off.'

// Params that only bust a cache; the recorder never sends them.
const IGNORED_PARAMS = new Set(['force', 'force_refresh'])

export function requestKey(method, url, params = {}) {
  const query = Object.entries(params || {})
    .filter(([k, v]) => v !== undefined && v !== null && !IGNORED_PARAMS.has(k))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')
  return `${method.toUpperCase()} ${url}${query ? `?${query}` : ''}`
}

// Later entries win, so a re-recorded request (the portfolio polled until synced) replaces the first.
export function buildTable(entries) {
  return new Map(entries.map(e => [requestKey(e.method, e.path, e.params), e]))
}

function reject(config, status, data) {
  const err = new Error(`Request failed with status code ${status}`)
  err.config = config
  err.response = { status, statusText: '', headers: {}, config, data }
  return Promise.reject(err)
}

export function makeAdapter(table) {
  return (config) => {
    const method = config.method || 'get'
    const key = requestKey(method, config.url, config.params)
    const hit = table.get(key)
    if (hit && hit.status < 400) {
      return Promise.resolve({ data: hit.body, status: hit.status, statusText: 'OK', headers: {}, config, request: {} })
    }
    if (hit) return reject(config, hit.status, hit.body)
    if (method.toLowerCase() !== 'get') return reject(config, 403, { detail: DEMO_WRITE_MESSAGE })
    console.warn('[demo] no recording for', key)
    return reject(config, 404, { detail: 'This part of the app is not in the demo.' })
  }
}

// Runs the page's clock from the recorded moment, so countdowns, "2h ago" and labels the
// server wrote ("Sun 1:00 PM") read as they did on the day, whenever the demo is opened.
export function anchorClock(atMs) {
  const RealDate = globalThis.Date
  const offset = atMs - RealDate.now()
  class DemoDate extends RealDate {
    constructor(...args) {
      if (args.length) super(...args)
      else super(RealDate.now() + offset)
    }
    static now() { return RealDate.now() + offset }
  }
  globalThis.Date = DemoDate
  return () => { globalThis.Date = RealDate }
}
