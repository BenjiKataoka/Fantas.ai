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

// news_type → chip styling. Presentational only, no LLM — the type is scraped.
const TYPE_STYLES = {
  INJURY:      { label: 'Injury',      cls: 'text-bear border-bear/30 bg-bear/10' },
  TRANSACTION: { label: 'Transaction', cls: 'text-teal-300 border-teal-400/30 bg-teal-400/10' },
  CONTRACT:    { label: 'Contract',    cls: 'text-brand border-brand/30 bg-brand/10' },
  DEPTH_CHART: { label: 'Depth Chart', cls: 'text-amber-300 border-amber-400/30 bg-amber-400/10' },
  PERFORMANCE: { label: 'Performance', cls: 'text-bull border-bull/30 bg-bull/10' },
  GENERAL:     { label: 'News',        cls: 'text-subtle border-line bg-raised' },
}

function TypeChip({ type }) {
  const s = TYPE_STYLES[type] || TYPE_STYLES.GENERAL
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide border ${s.cls}`}>
      {s.label}
    </span>
  )
}

const FILTERS = [
  { key: 'all',            label: 'All' },
  { key: 'BULLISH',        label: 'Bullish' },
  { key: 'BEARISH',        label: 'Bearish' },
  { key: 'NEUTRAL',        label: 'Neutral' },
  { key: 'contradictions', label: 'Contradictions' },
]

// Unified article card. Every scraped item renders as a readable, clickable article;
// the AI analysis (summary / short-long term / contradiction) is layered on top only
// when a full Gemini card exists. Rule-filter and rostered items still show a signal badge.
function NewsCard({ item, playerLabel, playerName }) {
  const [expanded, setExpanded] = useState(false)
  const isFull = item.analysis_tier === 'full'
  const hasBadge = !!item.stock_direction
  const url = item.source_url
  const body = item.news_body?.trim()
  const longBody = body && body.length > 220

  // The whole card is the link when a source URL exists. Interactive children
  // (Read more) call stopPropagation so they don't also trigger navigation.
  const openSource = () => { if (url) window.open(url, '_blank', 'noopener,noreferrer') }
  const onKeyDown = (e) => { if (url && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openSource() } }

  const Headline = url ? (
    <span className="group inline-flex items-start gap-1 text-sm font-semibold text-content group-hover/card:text-brand leading-snug transition-colors">
      <span>{item.headline}</span>
      <span className="text-subtle/50 shrink-0 mt-0.5" aria-hidden>↗</span>
    </span>
  ) : (
    <p className="text-sm font-semibold text-content leading-snug">{item.headline}</p>
  )

  return (
    <article
      onClick={url ? openSource : undefined}
      onKeyDown={url ? onKeyDown : undefined}
      role={url ? 'link' : undefined}
      tabIndex={url ? 0 : undefined}
      aria-label={url ? `Open article: ${item.headline}` : undefined}
      className={`group/card bg-surface border border-line rounded-xl p-4 flex flex-col gap-2.5 transition-colors ${
        url ? 'cursor-pointer hover:border-brand/40 hover:bg-surface/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <PlayerAvatar playerId={item.player_id} name={playerName} size={isFull ? 'lg' : 'md'} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-semibold ${isFull ? 'text-brand' : 'text-subtle'}`}>{playerLabel}</span>
              <TypeChip type={item.news_type} />
            </div>
            <div className="mt-1">{Headline}</div>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-subtle/70">{formatSource(item.source)}</p>
          <p className="text-xs text-subtle/50 font-mono">{relativeTime(item.published_at)}</p>
        </div>
      </div>

      {/* Raw scraped body — the article itself, always shown when present */}
      {body && (
        <div>
          <p className={`text-xs text-content/80 leading-relaxed ${!expanded && longBody ? 'line-clamp-3' : ''}`}>
            {body}
          </p>
          {longBody && (
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(v => !v) }}
              className="mt-1 text-xs text-subtle hover:text-brand font-medium transition-colors"
            >
              {expanded ? 'Show less' : 'Read more'}
            </button>
          )}
        </div>
      )}

      {/* AI summary (full cards only) */}
      {isFull && item.summary && (
        <p className="text-sm text-content/90 leading-relaxed border-l-2 border-brand/40 pl-3">{item.summary}</p>
      )}

      {/* Signal / stock badge row — free rule-filter or full Gemini direction */}
      {(hasBadge || item.confidence_score != null) && (
        <div className="flex items-center gap-3">
          {hasBadge && <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} size={isFull ? undefined : 'sm'} />}
          {item.confidence_score != null && (
            <span className="text-xs text-subtle font-mono tabular-nums">{Math.round(item.confidence_score * 100)}% confidence</span>
          )}
          {isFull && item.analysis_model && <span className="text-xs text-subtle/50 font-mono ml-auto">{item.analysis_model}</span>}
        </div>
      )}

      {/* Full-analysis enrichment */}
      {isFull && item.contradictions_flagged && <ContradictionAlert detail={item.contradiction_detail} />}

      {isFull && (item.short_term_impact || item.long_term_impact) && (
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

      {isFull && item.context_notes && (
        <p className="text-xs text-subtle italic border-t border-line pt-2">{item.context_notes}</p>
      )}
    </article>
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
          {filtered.map(item => (
            <NewsCard
              key={item.news_id}
              item={item}
              playerLabel={getPlayerLabel(item)}
              playerName={playerMap[item.player_id]?.name || ''}
            />
          ))}
        </div>
      )}
    </div>
  )
}
