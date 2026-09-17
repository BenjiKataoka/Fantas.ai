import { useState } from 'react'

/**
 * PlayerAvatar — player headshot from Sleeper's CDN, keyed by the Sleeper player_id
 * that every roster/news/startsit record already carries. No API call, no token cost.
 * Falls back to the player's initials on a missing/broken image (e.g. team DEF, rookies
 * without a photo yet).
 *
 * Props:
 *   playerId — Sleeper player_id (string)
 *   name     — full name (for initials fallback + alt text)
 *   size     — pixel diameter (default 32)
 */
const SIZES = {
  sm: 28,
  md: 32,
  lg: 44,
}

function initials(name = '') {
  const parts = name.trim().split(/\s+/)
  if (!parts[0]) return '?'
  const first = parts[0][0] || ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

export default function PlayerAvatar({ playerId, name = '', size = 'md' }) {
  const [failed, setFailed] = useState(false)
  const px = typeof size === 'number' ? size : (SIZES[size] || 32)
  const url = playerId ? `https://sleepercdn.com/content/nfl/players/${playerId}.jpg` : null

  if (!url || failed) {
    return (
      <span
        className="inline-flex items-center justify-center rounded-full bg-raised border border-line text-subtle font-semibold shrink-0"
        style={{ width: px, height: px, fontSize: px * 0.36 }}
        aria-label={name}
      >
        {initials(name)}
      </span>
    )
  }

  return (
    <img
      src={url}
      alt={name}
      loading="lazy"
      onError={() => setFailed(true)}
      className="rounded-full object-cover object-top bg-raised border border-line shrink-0"
      style={{ width: px, height: px }}
    />
  )
}
