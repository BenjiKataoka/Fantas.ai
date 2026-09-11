import { useState, useEffect, useCallback, useMemo } from 'react'
import { getTrackerList, unstarPlayer, refreshPlayer } from '../services/api'
import { useApp } from '../context/AppContext'
import TrackerCard from '../components/TrackerCard'
import PlayerSearchModal from '../components/PlayerSearchModal'
import Spinner from '../components/Spinner'

const POLL_INTERVAL_MS = 5000  // re-fetch every 5s while any profile is generating

export default function PlayerTracker() {
  const { credentials } = useApp()

  const [players, setPlayers]         = useState([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)
  const [showModal, setShowModal]     = useState(false)
  const [refreshingId, setRefreshingId] = useState(null)

  const fetchList = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    setError(null)
    try {
      const res = await getTrackerList()
      setPlayers(res.data.tracked_players || [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load tracked players.')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchList()
  }, [fetchList])

  // Poll silently while any player is still generating a profile
  const anyGenerating = useMemo(
    () => players.some(p => !p.profile_ready),
    [players]
  )

  useEffect(() => {
    if (!anyGenerating) return
    const id = setInterval(() => fetchList(true), POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [anyGenerating, fetchList])

  const starredIds = useMemo(
    () => new Set(players.map(p => p.player_id)),
    [players]
  )

  const handleStar = (playerId) => {
    // Add an optimistic placeholder immediately so the card appears right away
    setPlayers(prev => [
      ...prev,
      { player_id: playerId, player_name: '…', profile_ready: false },
    ])
    setShowModal(false)
    // Then re-fetch to get actual name/position
    setTimeout(() => fetchList(true), 800)
  }

  const handleUnstar = async (playerId) => {
    try {
      await unstarPlayer(playerId)
      setPlayers(prev => prev.filter(p => p.player_id !== playerId))
    } catch {
      // silently ignore — player stays in list
    }
  }

  const handleRefresh = async (playerId) => {
    setRefreshingId(playerId)
    try {
      await refreshPlayer(playerId)
      // Mark as generating so polling picks it up
      setPlayers(prev =>
        prev.map(p => p.player_id === playerId ? { ...p, profile_ready: false } : p)
      )
    } catch {
      // silently ignore
    } finally {
      setRefreshingId(null)
    }
  }

  if (!credentials) {
    return (
      <div className="text-center py-16 text-gray-600">
        <p className="text-sm">Set up your league in Settings first.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Player Tracker</h1>
          {players.length > 0 && (
            <p className="text-sm text-gray-500 mt-0.5">
              {players.length} player{players.length !== 1 ? 's' : ''} starred
              {anyGenerating && <span className="ml-2 text-blue-400">· generating profiles…</span>}
            </p>
          )}
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          + Add Player
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && !players.length && <Spinner label="Loading watchlist…" />}

      {/* Empty state */}
      {!loading && !error && players.length === 0 && (
        <div className="text-center py-20 text-gray-600">
          <p className="text-sm mb-1">Your watchlist is empty.</p>
          <p className="text-xs mb-5">Star players to get AI stock profiles, ADP trends, and sentiment analysis.</p>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            + Add your first player
          </button>
        </div>
      )}

      {/* Player cards */}
      {players.length > 0 && (
        <div className="flex flex-col gap-4">
          {players.map(p => (
            <TrackerCard
              key={p.player_id}
              player={p}
              onUnstar={handleUnstar}
              onRefresh={handleRefresh}
            />
          ))}
        </div>
      )}

      {/* Search modal */}
      {showModal && (
        <PlayerSearchModal
          starredIds={starredIds}
          onStar={handleStar}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}
