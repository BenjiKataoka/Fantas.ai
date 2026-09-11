import { useState, useEffect, useRef } from 'react'
import { searchPlayers, starPlayer } from '../services/api'

const POS_COLORS = {
  QB: 'text-red-400', RB: 'text-green-400',
  WR: 'text-blue-400', TE: 'text-yellow-400', K: 'text-gray-400',
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
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl">
        {/* Search input */}
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <span className="text-gray-500 text-sm">🔍</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search player name…"
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
            />
            {searching && (
              <div className="w-4 h-4 border-2 border-gray-700 border-t-blue-500 rounded-full animate-spin shrink-0" />
            )}
          </div>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {error && (
            <p className="text-xs text-red-400 px-4 py-3">{error}</p>
          )}

          {!error && query.length < 2 && (
            <p className="text-xs text-gray-600 px-4 py-4 text-center">
              Type at least 2 characters to search
            </p>
          )}

          {!error && query.length >= 2 && !searching && results.length === 0 && (
            <p className="text-xs text-gray-600 px-4 py-4 text-center">
              No players found. Try loading your roster first to warm the player cache.
            </p>
          )}

          {results.map(p => {
            const alreadyStarred = starredIds.has(p.player_id)
            const isStarring     = starring === p.player_id

            return (
              <div
                key={p.player_id}
                className="flex items-center justify-between px-4 py-3 border-b border-gray-800/50 last:border-0 hover:bg-gray-800/40 transition-colors"
              >
                <div>
                  <span className="text-sm text-white font-medium">{p.name}</span>
                  <span className="text-xs text-gray-500 ml-2">
                    <span className={POS_COLORS[p.position] || 'text-gray-400'}>{p.position}</span>
                    {p.nfl_team && <span className="ml-1">{p.nfl_team}</span>}
                  </span>
                </div>
                <button
                  onClick={() => handleStar(p)}
                  disabled={alreadyStarred || isStarring}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg border transition-colors shrink-0 ml-3 ${
                    alreadyStarred
                      ? 'bg-yellow-900/20 border-yellow-800/50 text-yellow-500 cursor-default'
                      : 'bg-blue-600 hover:bg-blue-500 border-blue-500 text-white disabled:opacity-50'
                  }`}
                >
                  {isStarring ? '…' : alreadyStarred ? '★ Starred' : '+ Star'}
                </button>
              </div>
            )
          })}
        </div>

        <div className="px-4 py-2.5 border-t border-gray-800">
          <p className="text-xs text-gray-700">
            Searches all NFL players. Hit Escape to close.
          </p>
        </div>
      </div>
    </div>
  )
}
