import { useState, useEffect, useRef } from 'react'
import { searchPlayers, starPlayer } from '../services/api'

const POS_COLORS = {
  QB: 'text-violet-300', RB: 'text-teal-300',
  WR: 'text-sky-300', TE: 'text-amber-300', K: 'text-subtle',
}

/**
 * PlayerSearchModal — overlay for searching and starring players.
 *
 * Props:
 *   starredIds — Set of player_ids already starred
 *   onStar     — fn(player_id) called after a successful star
 *   onClose    — fn() closes the modal
 */
export default function PlayerSearchModal({ starredIds, onStar, onClose }) {
  const [query, setQuery]     = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [starring, setStarring]   = useState(null)  // player_id being starred
  const [error, setError]         = useState(null)
  const inputRef = useRef(null)

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Debounced search
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    const timer = setTimeout(async () => {
      setSearching(true)
      setError(null)
      try {
        const res = await searchPlayers(query.trim())
        setResults(res.data.players || [])
      } catch {
        setError('Search failed. Make sure your roster is loaded.')
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const handleStar = async (player) => {
    if (starredIds.has(player.player_id)) return
    setStarring(player.player_id)
    setError(null)
    try {
      await starPlayer(player.player_id)
      onStar(player.player_id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to star player.')
    } finally {
      setStarring(null)
    }
  }

  // Close on backdrop click
  const handleBackdrop = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-24 z-50 px-4"
      onClick={handleBackdrop}
    >
      <div className="bg-surface border border-line rounded-xl w-full max-w-md shadow-2xl">
        {/* Search input */}
        <div className="p-4 border-b border-line">
          <div className="flex items-center gap-3">
            <span className="text-subtle text-sm">🔍</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search player name…"
              className="flex-1 bg-transparent text-sm text-content placeholder-subtle/60 focus:outline-none"
            />
            {searching && (
              <div className="w-4 h-4 border-2 border-line border-t-brand rounded-full animate-spin shrink-0" />
            )}
          </div>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {error && <p className="text-xs text-bear px-4 py-3">{error}</p>}

          {!error && query.length < 2 && (
            <p className="text-xs text-subtle/70 px-4 py-4 text-center">Type at least 2 characters to search</p>
          )}

          {!error && query.length >= 2 && !searching && results.length === 0 && (
            <p className="text-xs text-subtle/70 px-4 py-4 text-center">
              No players found. Try loading your roster first to warm the player cache.
            </p>
          )}

          {results.map(p => {
            const alreadyStarred = starredIds.has(p.player_id)
            const isStarring     = starring === p.player_id

            return (
              <div
                key={p.player_id}
                className="flex items-center justify-between px-4 py-3 border-b border-line/50 last:border-0 hover:bg-raised transition-colors"
              >
                <div>
                  <span className="text-sm text-content font-medium">{p.name}</span>
                  <span className="text-xs text-subtle ml-2 font-mono">
                    <span className={POS_COLORS[p.position] || 'text-subtle'}>{p.position}</span>
                    {p.nfl_team && <span className="ml-1">{p.nfl_team}</span>}
                  </span>
                </div>
                <button
                  onClick={() => handleStar(p)}
                  disabled={alreadyStarred || isStarring}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg border transition-all shrink-0 ml-3 ${
                    alreadyStarred
                      ? 'bg-warn/10 border-warn/30 text-warn cursor-default'
                      : 'bg-brand hover:brightness-110 border-brand text-brand-fg disabled:opacity-50'
                  }`}
                >
                  {isStarring ? '…' : alreadyStarred ? '★ Starred' : '+ Star'}
                </button>
              </div>
            )
          })}
        </div>

        <div className="px-4 py-2.5 border-t border-line">
          <p className="text-xs text-subtle/60">Searches all NFL players. Hit Escape to close.</p>
        </div>
      </div>
    </div>
  )
}
