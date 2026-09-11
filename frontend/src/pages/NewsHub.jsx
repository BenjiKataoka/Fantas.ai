import { useState, useMemo } from 'react'
import { useApp } from '../context/AppContext'
import Spinner from '../components/Spinner'
import StockBadge from '../components/StockBadge'
import ContradictionAlert from '../components/ContradictionAlert'

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function formatSource(source) {
  if (!source) return ''
  return source.charAt(0).toUpperCase() + source.slice(1).toLowerCase()
}

// ── Filter tabs ───────────────────────────────────────────────────────────────

const FILTERS = [
  { key: 'all',            label: 'All' },
  { key: 'BULLISH',        label: 'Bullish' },
  { key: 'BEARISH',        label: 'Bearish' },
  { key: 'NEUTRAL',        label: 'Neutral' },
  { key: 'contradictions', label: 'Contradictions' },
]

// ── Full analysis card (starred player, Gemini ran) ───────────────────────────

function FullCard({ item, playerLabel }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="text-xs font-semibold text-blue-400">{playerLabel}</span>
          <p className="text-sm font-semibold text-white mt-0.5 leading-snug">{item.headline}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-gray-500">{formatSource(item.source)}</p>
          <p className="text-xs text-gray-600">{relativeTime(item.published_at)}</p>
        </div>
      </div>

      {/* Summary */}
      {item.summary && (
        <p className="text-sm text-gray-300 leading-relaxed">{item.summary}</p>
      )}

      {/* Stock direction + confidence */}
      <div className="flex items-center gap-3">
        <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} />
        {item.confidence_score != null && (
          <span className="text-xs text-gray-500 font-mono">
            {Math.round(item.confidence_score * 100)}% confidence
          </span>
        )}
        {item.analysis_model && (
          <span className="text-xs text-gray-700 ml-auto">{item.analysis_model}</span>
        )}
      </div>

      {/* Contradiction alert */}
      {item.contradictions_flagged && (
        <ContradictionAlert detail={item.contradiction_detail} />
      )}

      {/* Impacts */}
      {(item.short_term_impact || item.long_term_impact) && (
        <div className="grid grid-cols-2 gap-3 pt-1">
          {item.short_term_impact && (
            <div className="bg-gray-800/60 rounded-lg p-3">
              <p className="text-xs font-semibold text-gray-500 mb-1">Short Term</p>
              <p className="text-xs text-gray-300 leading-snug">{item.short_term_impact}</p>
            </div>
          )}
          {item.long_term_impact && (
            <div className="bg-gray-800/60 rounded-lg p-3">
              <p className="text-xs font-semibold text-gray-500 mb-1">Long Term</p>
              <p className="text-xs text-gray-300 leading-snug">{item.long_term_impact}</p>
            </div>
          )}
        </div>
      )}

      {/* Context notes */}
      {item.context_notes && (
        <p className="text-xs text-gray-500 italic border-t border-gray-800 pt-2">{item.context_notes}</p>
      )}
    </div>
  )
}

// ── Signal-only card (rostered player or rule-filter result) ──────────────────

function SignalCard({ item, playerLabel }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <span className="text-xs font-semibold text-gray-500">{playerLabel}</span>
          <p className="text-sm text-gray-300 mt-0.5 leading-snug">{item.headline}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-gray-600">{formatSource(item.source)}</p>
          <p className="text-xs text-gray-700">{relativeTime(item.published_at)}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} size="sm" />
        {item.confidence_score != null && (
          <span className="text-xs text-gray-600 font-mono">
            {Math.round(item.confidence_score * 100)}%
          </span>
        )}
      </div>
    </div>
  )
}

// ── Pending card ──────────────────────────────────────────────────────────────

function PendingCard({ item, playerLabel }) {
  return (
    <div className="bg-gray-900 border border-gray-800/50 rounded-xl p-4 opacity-60">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="text-xs font-semibold text-gray-600">{playerLabel}</span>
          <p className="text-sm text-gray-400 mt-0.5">{item.headline}</p>
        </div>
        <span className="text-xs text-gray-600 shrink-0">{relativeTime(item.published_at)}</span>
      </div>
      <p className="text-xs text-gray-600 mt-2 italic">Analysis pending…</p>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewsHub() {
  const { rosterData, newsData, newsLoading, fetchNews } = useApp()
  const [activeFilter, setActiveFilter] = useState('all')

  // Build player lookup from roster
  const playerMap = useMemo(() => {
    if (!rosterData?.roster) return {}
    const map = {}
    for (const p of rosterData.roster) {
      map[p.player_id] = { name: p.name, position: p.position, nfl_team: p.nfl_team }
    }
    return map
  }, [rosterData])

  const items = newsData?.news ?? []

  const filtered = useMemo(() => {
    if (activeFilter === 'all') return items
    if (activeFilter === 'contradictions') return items.filter(i => i.contradictions_flagged)
    return items.filter(i => i.stock_direction === activeFilter)
  }, [items, activeFilter])

  const contradictionCount = useMemo(
    () => items.filter(i => i.contradictions_flagged).length,
    [items]
  )

  function getPlayerLabel(item) {
    const p = playerMap[item.player_id]
    if (!p) return `Player ${item.player_id}`
    return `${p.name} · ${p.position}${p.nfl_team ? ' · ' + p.nfl_team : ''}`
  }

  return (
    <div className="max-w-3xl">
      {/* Page header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold">News Hub</h1>
          {newsData && (
            <p className="text-sm text-gray-500 mt-0.5">
              {items.length} items · last 7 days
              {newsData.season_type && (
                <span className="ml-2 capitalize text-gray-600">({newsData.season_type}season)</span>
              )}
            </p>
          )}
        </div>
        <button
          onClick={() => fetchNews(true)}
          disabled={newsLoading}
          className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 text-xs font-medium rounded-lg border border-gray-700 transition-colors"
        >
          {newsLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {FILTERS.map(f => {
          const count = f.key === 'all' ? items.length
            : f.key === 'contradictions' ? contradictionCount
            : items.filter(i => i.stock_direction === f.key).length
          const isActive = activeFilter === f.key
          return (
            <button
              key={f.key}
              onClick={() => setActiveFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                isActive
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-gray-900 border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-300'
              }`}
            >
              {f.label}
              {count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs font-mono ${
                  isActive ? 'bg-blue-500/50 text-blue-200' : 'bg-gray-800 text-gray-500'
                }`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Loading */}
      {newsLoading && !newsData && <Spinner label="Loading news feed…" />}

      {/* Empty state — no news at all */}
      {!newsLoading && !items.length && (
        <div className="text-center py-16 text-gray-600">
          <p className="text-sm">No news found for your roster.</p>
          <p className="text-xs mt-1">Make sure your league is set up in Settings.</p>
        </div>
      )}

      {/* No results for current filter */}
      {!newsLoading && items.length > 0 && filtered.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <p className="text-sm">No items match this filter.</p>
        </div>
      )}

      {/* News feed */}
      {filtered.length > 0 && (
        <div className="flex flex-col gap-3">
          {filtered.map(item => {
            const label = getPlayerLabel(item)
            if (item.analysis_tier === 'full') {
              return <FullCard key={item.news_id} item={item} playerLabel={label} />
            }
            if (item.analysis_tier === 'signal_only') {
              return <SignalCard key={item.news_id} item={item} playerLabel={label} />
            }
            return <PendingCard key={item.news_id} item={item} playerLabel={label} />
          })}
        </div>
      )}
    </div>
  )
}
