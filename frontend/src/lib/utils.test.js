// Run: node src/lib/utils.test.js
// relativeTime replaced four near-copies that disagreed on edges, so the edges are pinned here.
import assert from 'node:assert/strict'
import { relativeTime, slotLabel, parseEspnCookies } from './utils.js'

const now = new Date('2026-09-22T12:00:00Z').getTime()
const at = (ms) => new Date(now - ms).toISOString()

assert.equal(relativeTime(null), '', 'null renders as empty, never "Invalid Date"')
assert.equal(relativeTime(undefined), '')
assert.equal(relativeTime(at(30 * 1000), now), 'just now')
assert.equal(relativeTime(at(5 * 60_000), now), '5m ago')
assert.equal(relativeTime(at(59 * 60_000), now), '59m ago')
assert.equal(relativeTime(at(60 * 60_000), now), '1h ago')
assert.equal(relativeTime(at(23 * 3600_000), now), '23h ago')
// The App.jsx copy stopped at hours and would have said "49h ago" here.
assert.equal(relativeTime(at(49 * 3600_000), now), '2d ago')
// App.jsx passes a Date plus its own ticking clock; both forms must work.
assert.equal(relativeTime(new Date(now - 3 * 60_000), now), '3m ago')

assert.equal(slotLabel('SUPER_FLEX'), 'SFLEX')
assert.equal(slotLabel('QB'), 'QB')

console.log('utils: all assertions passed')

// parseEspnCookies: the input is whatever a person pasted, so the shapes it must survive
// are the bookmarklet's output, a raw Cookie header, and a half-finished paste.
{
  const bookmarklet = 'espn_s2=AEBxyz%2Fabc123; SWID={1F02C74E-D45A-417F-C1A1-F31780BE280A}'
  const r = parseEspnCookies(bookmarklet)
  assert.equal(r.espn_s2, 'AEBxyz%2Fabc123')
  assert.equal(r.swid, '{1F02C74E-D45A-417F-C1A1-F31780BE280A}')

  // A real Cookie header carries a pile of unrelated cookies around them.
  const header = 'edition=espn-en-us; SWID={ABC-123}; country=us; espn_s2=deadbeef; region=ccpa'
  const h = parseEspnCookies(header)
  assert.equal(h.espn_s2, 'deadbeef')
  assert.equal(h.swid, '{ABC-123}')

  // Braces get lost when people copy out of DevTools; put them back.
  assert.equal(parseEspnCookies('espn_s2=x; SWID=ABC-123').swid, '{ABC-123}')

  // Both or nothing: a partial paste must not half-fill the form.
  assert.equal(parseEspnCookies('espn_s2=onlythis'), null, 'espn_s2 alone is not enough')
  assert.equal(parseEspnCookies('SWID={ABC}'), null, 'SWID alone is not enough')
  assert.equal(parseEspnCookies(''), null)
  assert.equal(parseEspnCookies(undefined), null)

  // A bare value pasted into the field is not a cookie string and must pass through.
  assert.equal(parseEspnCookies('AEBxyz%2Fabc123'), null, 'a plain value is not a paste')

  console.log('parseEspnCookies: all assertions passed')
}
