// Run: node src/demo/demoAdapter.test.js
// The demo's whole network is this file's lookup, so its edges are pinned here.
import assert from 'node:assert/strict'
import { requestKey, buildTable, makeAdapter, anchorClock, DEMO_WRITE_MESSAGE } from './demoAdapter.js'

// Keys: param order, cache-busting params and number-vs-string must not matter.
assert.equal(requestKey('get', '/waivers', { platform: 'ESPN', league_id: '1' }), 'GET /waivers?league_id=1&platform=ESPN')
assert.equal(requestKey('get', '/roster', { league_id: '1', force: true }), requestKey('GET', '/roster', { league_id: '1' }))
assert.equal(requestKey('get', '/news', { force_refresh: false }), 'GET /news')
assert.equal(requestKey('get', '/tape', { week: 2 }), requestKey('get', '/tape', { week: '2' }))
assert.equal(requestKey('get', '/leagues', { sleeper_username: undefined }), 'GET /leagues')
assert.equal(requestKey('get', '/leagues'), 'GET /leagues')

const table = buildTable([
  { method: 'GET', path: '/leagues', params: {}, status: 200, body: { leagues: [1] } },
  { method: 'POST', path: '/waivers/analyze/7', params: { league_id: '1' }, status: 200, body: { verdict: 'ADD' } },
])
const adapter = makeAdapter(table)
const realWarn = console.warn
const warned = []
console.warn = (...a) => warned.push(a.join(' '))
try {
  assert.deepEqual((await adapter({ method: 'get', url: '/leagues', params: { force: true } })).data, { leagues: [1] })
  assert.equal((await adapter({ method: 'post', url: '/waivers/analyze/7', params: { league_id: '1' } })).data.verdict, 'ADD')
  await assert.rejects(adapter({ method: 'put', url: '/settings' }),
    e => e.response.status === 403 && e.response.data.detail === DEMO_WRITE_MESSAGE)
  await assert.rejects(adapter({ method: 'get', url: '/admin/users' }), e => e.response.status === 404)
  assert.equal(warned.length, 1, 'only a missed GET warns; a refused write is expected behaviour')
} finally {
  console.warn = realWarn
}

// Clock: starts at the recorded moment, keeps ticking, leaves explicit dates alone.
const recorded = Date.parse('2020-01-01T12:00:00Z')
const restore = anchorClock(recorded)
try {
  assert.ok(Math.abs(Date.now() - recorded) < 1000)
  assert.ok(Math.abs(new Date().getTime() - recorded) < 1000)
  assert.equal(new Date(0).getTime(), 0)
  assert.equal(Date.parse('2020-01-02T00:00:00Z') - Date.parse('2020-01-01T00:00:00Z'), 86400000)
  assert.ok(new Date() instanceof Date)
  const until = Date.now() + 20
  while (Date.now() < until) { /* the anchored clock must still move */ }
} finally {
  restore()
}
assert.ok(Date.now() - recorded > 1000 * 86400, 'restore puts the real clock back')

console.log('demoAdapter: all assertions passed')
