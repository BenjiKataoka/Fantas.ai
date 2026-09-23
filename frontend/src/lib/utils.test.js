// Run: node src/lib/utils.test.js
// relativeTime replaced four near-copies that disagreed on edges, so the edges are pinned here.
import assert from 'node:assert/strict'
import { relativeTime, slotLabel } from './utils.js'

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
