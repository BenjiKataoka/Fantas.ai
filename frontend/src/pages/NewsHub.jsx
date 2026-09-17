import { useState, useMemo } from 'react'
import { useApp } from '../context/AppContext'
import StockBadge from '../components/StockBadge'
import ContradictionAlert from '../components/ContradictionAlert'
import PlayerAvatar from '../components/PlayerAvatar'
import { CardListSkeleton } from '../components/Skeletons'

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

const FILTERS = [
  { key: 'all',            label: 'All' },
  { key: 'BULLISH',        label: 'Bullish' },
  { key: 'BEARISH',        label: 'Bearish' },
  { key: 'NEUTRAL',        label: 'Neutral' },
  { key: 'contradictions', label: 'Contradictions' },
]

// ── Full analysis card (starred player, Gemini ran) ───────────────────────────
function FullCard({ item, playerLabel, playerName }) {
  return (
    <div className="bg-surface border border-line rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <PlayerAvatar playerId={item.player_id} name={playerName} size="lg" />
          <div className="min-w-0">
            <span className="text-xs font-semibold text-brand">{playerLabel}</span>
            <p className="text-sm font-semibold text-content mt-0.5 leading-snug">{item.headline}</p>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-subtle">{formatSource(item.source)}</p>
          <p className="text-xs text-subtle/70 font-mono">{relativeTime(item.published_at)}</p>
        </div>
      </div>

      {item.summary && <p className="text-sm text-content/90 leading-relaxed">{item.summary}</p>}

      <div className="flex items-center gap-3">
        <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} />
        {item.confidence_score != null && (
          <span className="text-xs text-subtle font-mono tabular-nums">{Math.round(item.confidence_score * 100)}% confidence</span>
        )}
        {item.analysis_model && <span className="text-xs text-subtle/50 font-mono ml-auto">{item.analysis_model}</span>}
      </div>

      {item.contradictions_flagged && <ContradictionAlert detail={item.contradiction_detail} />}

      {(item.short_term_impact || item.long_term_impact) && (
        <div className="grid grid-cols-2 gap-3 pt-1">
          {item.short_term_impact && (
            <div className="bg-raised rounded-lg p-3">
              <p className="text-xs font-semibold text-subtle uppercase tracking-wide mb-1">Short Term</p>
              <p className="text-xs text-content/80 leading-snug">{item.short_term_impact}</p>
            </div>
          )}
          {item.long_term_impact && (
            <div className="bg-raised rounded-lg p-3">
              <p className="text-xs font-semibold text-subtle uppercase tracking-wide mb-1">Long Term</p>
              <p className="text-xs text-content/80 leading-snug">{item.long_term_impact}</p>
            </div>
          )}
        </div>
      )}

      {item.context_notes && (
        <p className="text-xs text-subtle italic border-t border-line pt-2">{item.context_notes}</p>
      )}
    </div>
  )
}

// ── Signal-only card (rostered player or rule-filter result) ──────────────────
function SignalCard({ item, playerLabel, playerName }) {
  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <PlayerAvatar playerId={item.player_id} name={playerName} size="md" />
          <div className="min-w-0">
            <span className="text-xs font-semibold text-subtle">{playerLabel}</span>
            <p className="text-sm text-content/90 mt-0.5 leading-snug">{item.headline}</p>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-subtle/70">{formatSource(item.source)}</p>
          <p className="text-xs text-subtle/50 font-mono">{relativeTime(item.published_at)}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} size="sm" />
        {item.confidence_score != null && (
          <span className="text-xs text-subtle font-mono tabular-nums">{Math.round(item.confidence_score * 100)}%</span>
        )}
      </div>
    </div>
  )
}

// ── Pending card ──────────────────────────────────────────────────────────────
function PendingCard({ item, playerLabel, playerName }) {
  return (
    <div className="bg-surface border border-line/60 rounded-xl p-4 opacity-60">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <PlayerAvatar playerId={item.player_id} name={playerName} size="md" />
          <div className="min-w-0">
            <span className="text-xs font-semibold text-subtle/60">{playerLabel}</span>
            <p className="text-sm text-subtle mt-0.5">{item.headline}</p>
          </div>
        </div>
        <span className="text-xs text-subtle/60 shrink-0 font-mono">{relativeTime(item.published_at)}</span>
      </div>
      <p className="text-xs text-subtle/60 mt-2 italic">Analysis pending…</p>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function NewsHub() {
  const { rosterData, newsData, newsLoading, fetchNews } = useApp()
  const [activeFilter, setActiveFilter] = useState('all')

  const playerMap = useMemo(() => {
    if (!rosterData?.roster) return {}
    const map = {}
    for (const p of rosterData.roster) map[p.player_id] = { name: p.name, position: p.position, nfl_team: p.nfl_team }
    return map
  }, [rosterData])

  const items = newsData?.news ?? []

  const filtered = useMemo(() => {
    if (activeFilter === 'all') return items
    if (activeFilter === 'contradictions') return items.filter(i => i.contradictions_flagged)
    return items.filter(i => i.stock_direction === activeFilter)
  }, [items, activeFilter])

  const contradictionCount = useMemo(() => items.filter(i => i.contradictions_flagged).length, [items])

  function getPlayerLabel(item) {
    const p = playerMap[item.player_id]
    if (!p) return `Player ${item.player_id}`
    return `${p.name} · ${p.position}${p.nfl_team ? ' · ' + p.nfl_team : ''}`
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-display font-bold text-content">News Hub</h1>
          {newsData && (
            <p className="text-sm text-subtle mt-0.5">
              {items.length} items · last 7 days
              {newsData.season_type && <span className="ml-2 capitalize text-subtle/60">({newsData.season_type}season)</span>}
            </p>
          )}
        </div>
        <button
          onClick={() => fetchNews(true)}
          disabled={newsLoading}
          className="px-3 py-1.5 bg-raised hover:bg-line disabled:opacity-40 text-subtle hover:text-content text-xs font-medium rounded-lg border border-line transition-colors"
        >
          {newsLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

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
                  ? 'bg-brand border-brand text-brand-fg'
                  : 'bg-surface border-line text-subtle hover:text-content'
              }`}
            >
              {f.label}
              {count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs font-mono tabular-nums ${
                  isActive ? 'bg-brand-fg/20 text-brand-fg' : 'bg-raised text-subtle'
                }`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {newsLoading && !newsData && <CardListSkeleton count={5} />}

      {!newsLoading && !items.length && (
        <div className="text-center py-16 text-subtle/70">
          <p className="text-sm">No news found for your roster.</p>
          <p className="text-xs mt-1">Make sure your league is set up in Settings.</p>
        </div>
      )}

      {!newsLoading && items.length > 0 && filtered.length === 0 && (
        <div className="text-center py-12 text-subtle/70">
          <p className="text-sm">No items match this filter.</p>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="flex flex-col gap-3">
          {filtered.map(item => {
            const label = getPlayerLabel(item)
            const pname = playerMap[item.player_id]?.name || ''
            if (item.analysis_tier === 'full') return <FullCard key={item.news_id} item={item} playerLabel={label} playerName={pname} />
            if (item.analysis_tier === 'signal_only') return <SignalCard key={item.news_id} item={item} playerLabel={label} playerName={pname} />
            return <PendingCard key={item.news_id} item={item} playerLabel={label} playerName={pname} />
          })}
        </div>
      )}
    </div>
  )
}
