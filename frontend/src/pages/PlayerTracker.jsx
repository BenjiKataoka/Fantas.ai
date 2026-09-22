import { LoadingDots } from '../components/Spinner'
import { REVEAL } from '@/lib/utils'
import { useState, useEffect, useMemo, useCallback } from 'react'
import { toast } from 'sonner'
import { getTrackerList, unstarPlayer, getSentimentHistory } from '../services/api'
import { useApp } from '../context/AppContext'
import PlayerAvatar from '../components/PlayerAvatar'
import InjuryBadge from '../components/InjuryBadge'
import StockBadge from '../components/StockBadge'
import StockSection from '../components/StockSection'
import TrendChart, { METRICS } from '../components/TrendChart'
import PlayerSearchModal from '../components/PlayerSearchModal'

const POS_COLORS = { QB: 'text-pos-qb', RB: 'text-pos-rb', WR: 'text-pos-wr', TE: 'text-pos-te', K: 'text-subtle' }
const RANGES = [{ k: '1w', label: '1W' }, { k: '1m', label: '1M' }, { k: 'season', label: 'Season' }]
const METRIC_KEYS = ['rank', 'rostered', 'sentiment', 'concern', 'adp']

// ── Rostered / Watchlist segmented switch ─────────────────────────────────────
function TabSwitch({ tab, onChange, counts }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-raised p-0.5 text-xs font-semibold">
      {['rostered', 'watchlist'].map(t => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`px-3 py-1.5 rounded-md capitalize transition-colors ${
            tab === t ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content'
          }`}
        >
          {t}<span className="ml-1.5 font-mono font-normal opacity-70">{counts[t]}</span>
        </button>
      ))}
    </div>
  )
}

// ── Player picker dropdown ────────────────────────────────────────────────────
function PlayerPicker({ players, selectedId, onSelect }) {
  const [open, setOpen] = useState(false)
  const sel = players.find(p => p.id === selectedId)

  return (
    <div className="relative flex-1 min-w-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border border-line bg-surface hover:border-brand/50 transition-colors"
      >
        {sel ? (
          <>
            <PlayerAvatar playerId={sel.id} name={sel.name} size="sm" />
            <span className="text-content font-medium truncate">{sel.name}</span>
            <span className={`font-mono text-xs font-semibold ${POS_COLORS[sel.position] || 'text-subtle'}`}>{sel.position}</span>
          </>
        ) : (
          <span className="text-subtle text-sm">Select a player...</span>
        )}
        <span className={`ml-auto text-subtle/60 text-xs transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute z-20 mt-1 w-full max-h-80 overflow-auto rounded-lg border border-line bg-surface shadow-xl no-scrollbar">
            {players.length === 0 && <div className="px-3 py-4 text-sm text-subtle text-center">No players.</div>}
            {players.map(p => (
              <button
                key={p.id}
                onClick={() => { onSelect(p.id); setOpen(false) }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-raised transition-colors ${
                  p.id === selectedId ? 'bg-raised' : ''
                }`}
              >
                <PlayerAvatar playerId={p.id} name={p.name} size="sm" />
                <span className="text-content text-sm truncate">{p.name}</span>
                {p.stock?.concern_level != null && (
                  <span className={`ml-auto h-1.5 w-1.5 rounded-full ${
                    p.stock.concern_level <= 3 ? 'bg-bull' : p.stock.concern_level <= 6 ? 'bg-warn' : 'bg-bear'
                  }`} />
                )}
                <span className={`${p.stock?.concern_level != null ? '' : 'ml-auto'} font-mono text-xs font-semibold ${POS_COLORS[p.position] || 'text-subtle'}`}>{p.position}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function PlayerTracker() {
  const { credentials, rosterData } = useApp()

  const [tab, setTab]                 = useState('rostered')
  const [watchlist, setWatchlist]     = useState([])
  const [selectedId, setSelectedId]   = useState(null)
  const [range, setRange]             = useState('season')
  const [metric, setMetric]           = useState('rank')
  const [history, setHistory]         = useState(null)
  const [histLoading, setHistLoading] = useState(false)
  const [showModal, setShowModal]     = useState(false)

  // ── Normalized player lists per tab ──
  const rostered = useMemo(() => (rosterData?.roster || []).map(p => ({
    id: p.player_id, name: p.name, position: p.position, team: p.nfl_team,
    injury_status: p.injury_status, stock: p.stock,
  })), [rosterData])

  const watch = useMemo(() => watchlist.map(p => ({
    id: p.player_id, name: p.player_name, position: p.position, team: p.nfl_team,
    injury_status: 'Active', stock: p.profile_ready ? p : null,
  })), [watchlist])

  const list = tab === 'rostered' ? rostered : watch
  const selected = list.find(p => p.id === selectedId) || null

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await getTrackerList()
      setWatchlist(res.data.tracked_players || [])
    } catch { /* watchlist optional */ }
  }, [])

  useEffect(() => { fetchWatchlist() }, [fetchWatchlist])

  // Keep a valid selection as the tab/list changes, default to the first player.
  useEffect(() => {
    if (!list.length) { setSelectedId(null); return }
    if (!list.some(p => p.id === selectedId)) setSelectedId(list[0].id)
  }, [list, selectedId])

  // Fetch history for the selected player + range.
  useEffect(() => {
    if (!selectedId) { setHistory(null); return }
    let cancelled = false
    setHistLoading(true)
    getSentimentHistory(selectedId, range)
      .then(res => { if (!cancelled) setHistory(res.data) })
      .catch(() => { if (!cancelled) setHistory(null) })
      .finally(() => { if (!cancelled) setHistLoading(false) })
    return () => { cancelled = true }
  }, [selectedId, range])

  const handleStar = (playerId) => {
    setShowModal(false)
    toast.success('Added to watchlist. Building their profile now.')
    setTab('watchlist')
    setTimeout(fetchWatchlist, 900)
  }
  const handleUnstar = async () => {
    if (!selected) return
    try {
      await unstarPlayer(selected.id)
      setWatchlist(prev => prev.filter(p => p.player_id !== selected.id))
      toast('Removed from watchlist')
    } catch { toast.error('Could not remove player') }
  }

  if (!credentials) {
    return <div className="text-center py-16 text-subtle/70 text-sm">Set up your league in Settings first.</div>
  }

  // Per-metric trend for the selected player, in "goodness" terms (up = better).
  const stats = (() => {
    const m = METRICS[metric]
    const vals = (history?.points || []).map(p => m.accessor(p)).filter(v => v != null)
    if (!vals.length) return null
    const first = vals[0], last = vals[vals.length - 1]
    return { m, first, last, improved: m.betterHigh ? last > first : last < first, changed: first !== last }
  })()

  return (
    <div className="max-w-3xl">
      {/* Header + tab switch */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-2xl font-display font-bold text-content">Player Tracker</h1>
        <TabSwitch tab={tab} onChange={setTab} counts={{ rostered: rostered.length, watchlist: watch.length }} />
      </div>

      {/* Picker row */}
      <div className="flex items-center gap-2 mb-6">
        <PlayerPicker players={list} selectedId={selectedId} onSelect={setSelectedId} />
        {tab === 'watchlist' && (
          <button
            onClick={() => setShowModal(true)}
            className="shrink-0 px-3 py-2 bg-brand hover:brightness-110 text-brand-fg text-sm font-semibold rounded-lg transition-all"
          >
            + Add
          </button>
        )}
      </div>

      {list.length === 0 ? (
        <div className="text-center py-20 text-subtle/70">
          {tab === 'rostered'
            ? <p className="text-sm">No roster loaded. Pick your league on the Dashboard.</p>
            : <>
                <p className="text-sm mb-1 text-subtle">Your watchlist is empty.</p>
                <p className="text-xs mb-5">Add players you're eyeing on the waiver wire or in trades.</p>
                <button onClick={() => setShowModal(true)} className="px-4 py-2 bg-brand hover:brightness-110 text-brand-fg text-sm font-semibold rounded-lg transition-all">+ Add your first player</button>
              </>}
        </div>
      ) : selected && (
        // key on the player id so selecting a new player remounts the card and replays
        // the staggered reveal below; metric/range toggles keep the same id (no retrigger).
        <div
          key={selected.id}
          className="bg-surface border border-line rounded-xl overflow-hidden"
        >
          {/* Player header */}
          <div className={`flex items-center gap-3 p-4 border-b border-line ${REVEAL}`} style={{ animationDelay: '0ms' }}>
            <PlayerAvatar playerId={selected.id} name={selected.name} size="lg" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-lg font-display font-semibold text-content">{selected.name}</span>
                <InjuryBadge status={selected.injury_status} />
              </div>
              <div className="text-xs text-subtle font-mono mt-0.5">
                <span className={POS_COLORS[selected.position] || ''}>{selected.position}</span> · {selected.team}
              </div>
            </div>
            <div className="ml-auto text-right">
              {stats ? (
                <>
                  <div className="text-2xl font-mono font-bold text-content tabular-nums leading-none" style={{ color: stats.m.color }}>
                    {stats.m.value(stats.last, selected.position)}
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-subtle/70">{stats.m.label}</div>
                </>
              ) : <span className="text-xs text-subtle">No data</span>}
            </div>
          </div>

          {/* Plain-English trend readout */}
          {stats && stats.changed && (
            <div className={`px-4 pt-3 -mb-1 ${REVEAL}`} style={{ animationDelay: '70ms' }}>
              <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${stats.improved ? 'text-bull' : 'text-bear'}`}>
                {stats.improved ? '▲ Trending up' : '▼ Trending down'}
                <span className="text-subtle font-normal font-mono text-xs">
                  {stats.m.value(stats.first, selected.position)} → {stats.m.value(stats.last, selected.position)} this {range === 'season' ? 'season' : range === '1m' ? 'month' : 'week'}
                </span>
              </span>
            </div>
          )}

          {/* Chart controls */}
          <div className={`flex items-center justify-between flex-wrap gap-2 px-4 pt-3 ${REVEAL}`} style={{ animationDelay: '140ms' }}>
            <div className="inline-flex rounded-lg border border-line bg-raised p-0.5">
              {METRIC_KEYS.map(k => (
                <button
                  key={k}
                  onClick={() => setMetric(k)}
                  className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                    metric === k ? 'text-content' : 'text-subtle hover:text-content'
                  }`}
                  style={metric === k ? { background: `color-mix(in srgb, ${METRICS[k].color} 13%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${METRICS[k].color} 35%, transparent)` } : undefined}
                >{METRICS[k].label}</button>
              ))}
            </div>
            <div className="inline-flex rounded-lg border border-line bg-raised p-0.5">
              {RANGES.map(r => (
                <button
                  key={r.k}
                  onClick={() => setRange(r.k)}
                  className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                    range === r.k ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content'
                  }`}
                >{r.label}</button>
              ))}
            </div>
          </div>

          {/* Chart */}
          <div className={`px-2 pb-2 pt-1 ${REVEAL}`} style={{ animationDelay: '210ms' }}>
            {histLoading && !history
              ? <div className="h-[210px] flex items-center justify-center text-subtle" role="status" aria-label="Loading chart"><LoadingDots className="text-xl" /></div>
              : <TrendChart points={history?.points || []} metric={metric} position={selected.position} />}
          </div>

          {/* Current profile (comprehensive) */}
          <div className={`border-t border-line ${REVEAL}`} style={{ animationDelay: '280ms' }}>
            <StockSection stock={selected.stock} />
          </div>

          {/* Watchlist-only remove */}
          {tab === 'watchlist' && (
            <div className={`px-4 pb-4 ${REVEAL}`} style={{ animationDelay: '350ms' }}>
              <button onClick={handleUnstar} className="text-xs text-subtle/70 hover:text-bear transition-colors">
                Remove from watchlist
              </button>
            </div>
          )}
        </div>
      )}

      {showModal && (
        <PlayerSearchModal
          starredIds={new Set(watchlist.map(p => p.player_id))}
          onStar={handleStar}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}
