import { useState, useEffect, useCallback, useMemo } from 'react'
import { toast } from 'sonner'
import { getTrackerList, unstarPlayer, refreshPlayer } from '../services/api'
import { useApp } from '../context/AppContext'
import TrackerCard from '../components/TrackerCard'
import PlayerSearchModal from '../components/PlayerSearchModal'
import { CardListSkeleton } from '../components/Skeletons'

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
    // Optimistic placeholder so the card appears immediately; re-fetch fills in real data.
    setPlayers(prev => [...prev, { player_id: playerId, player_name: '…', profile_ready: false }])
    setShowModal(false)
    toast.success('Player starred — generating profile…')
    setTimeout(() => fetchList(true), 800)
  }

  const handleUnstar = async (playerId) => {
    try {
      await unstarPlayer(playerId)
      setPlayers(prev => prev.filter(p => p.player_id !== playerId))
      toast('Removed from watchlist')
    } catch {
      toast.error('Could not remove player')
    }
  }

  const handleRefresh = async (playerId) => {
    setRefreshingId(playerId)
    try {
      await refreshPlayer(playerId)
      setPlayers(prev => prev.map(p => p.player_id === playerId ? { ...p, profile_ready: false } : p))
      toast.success('Re-running analysis…')
    } catch {
      toast.error('Refresh failed')
    } finally {
      setRefreshingId(null)
    }
  }

  if (!credentials) {
    return (
      <div className="text-center py-16 text-subtle/70">
        <p className="text-sm">Set up your league in Settings first.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-display font-bold text-content">Player Tracker</h1>
          {players.length > 0 && (
            <p className="text-sm text-subtle mt-0.5">
              {players.length} player{players.length !== 1 ? 's' : ''} starred
              {anyGenerating && <span className="ml-2 text-brand">· generating profiles…</span>}
            </p>
          )}
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-brand hover:brightness-110 text-brand-fg text-sm font-semibold rounded-lg transition-all"
        >
          + Add Player
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-bear/10 border border-bear/30 rounded-lg text-bear text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && !players.length && <CardListSkeleton count={3} />}

      {/* Empty state */}
      {!loading && !error && players.length === 0 && (
        <div className="text-center py-20 text-subtle/70">
          <p className="text-sm mb-1 text-subtle">Your watchlist is empty.</p>
          <p className="text-xs mb-5">Star players to get AI stock profiles, ADP trends, and sentiment analysis.</p>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 bg-brand hover:brightness-110 text-brand-fg text-sm font-semibold rounded-lg transition-all"
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
