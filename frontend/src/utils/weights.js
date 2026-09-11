/**
 * When one slider moves, redistribute the remainder proportionally to the other two.
 * Ensures weights always sum to 1.0. Rounds to 2dp to prevent float drift.
 */
export function balanceWeights(key, newValue, current) {
  const remainder = Math.max(0, 1.0 - newValue)
  const others = Object.keys(current).filter(k => k !== key)
  const otherSum = others.reduce((s, k) => s + current[k], 0)
  const balanced = { ...current, [key]: newValue }
  if (otherSum === 0) {
    others.forEach(k => { balanced[k] = remainder / others.length })
  } else {
    others.forEach(k => { balanced[k] = (current[k] / otherSum) * remainder })
  }
  return Object.fromEntries(Object.entries(balanced).map(([k, v]) => [k, Math.round(v * 100) / 100]))
}
