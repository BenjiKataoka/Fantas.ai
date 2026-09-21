import { Star, TriangleAlert } from 'lucide-react'
import StockBadge from './StockBadge'
import ConcernMeter from './ConcernMeter'
import SentimentGauge from './SentimentGauge'

function relativeTime(isoStr) {
  if (!isoStr) return null
  const diff = Date.now() - new Date(isoStr).getTime()
  const hrs = Math.floor(diff / 3600000)
  if (hrs < 1)  return 'just now'
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function ADPTrendBadge({ adp_trend }) {
  const trend = adp_trend?.trend
  const delta = adp_trend?.delta
  if (!trend) return null

  const styles = {
    RISING:  { icon: '↑', color: 'text-bull',   bg: 'bg-bull/10 border-bull/30' },
    FALLING: { icon: '↓', color: 'text-bear',   bg: 'bg-bear/10 border-bear/30' },
    STABLE:  { icon: '→', color: 'text-subtle', bg: 'bg-raised border-line'     },
  }
  const s = styles[trend] ?? styles.STABLE

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold ${s.bg} ${s.color}`}>
      <span>{s.icon}</span>
      <span>ADP {trend}</span>
      {delta != null && delta !== 0 && (
        <span className="font-mono tabular-nums opacity-70">{delta > 0 ? '+' : ''}{delta.toFixed(1)}</span>
      )}
    </span>
  )
}

function FactorList({ items, type }) {
  if (!items?.length) return null
  const isGood  = type === 'bullish'
  const textCol = isGood ? 'text-bull' : 'text-bear'
  const dotCol  = isGood ? 'bg-bull' : 'bg-bear'

  return (
    <div>
      <p className={`text-xs font-semibold mb-1.5 ${textCol}`}>{isGood ? 'Bullish' : 'Bearish'}</p>
      <ul className="flex flex-col gap-1">
        {items.slice(0, 4).map((f, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${dotCol}`} />
            <span className="text-xs text-subtle leading-snug">{f}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * TrackerCard: full profile card for a starred player.
 * props: player (from GET /api/tracker), onUnstar(id), onRefresh(id)
 */
export default function TrackerCard({ player, onUnstar, onRefresh }) {
  const {
    player_id, player_name, position, nfl_team, profile_ready,
    overall_direction, overall_magnitude,
    concern_level, concern_summary, combined_score,
    bullish_factors, bearish_factors,
    sentiment_score, sentiment_label, dominant_themes, contrarian_flag, sentiment_vs_stock,
    short_term_outlook, long_term_outlook,
    draft_recommendation, adp_trend, historical_context, last_full_analysis,
  } = player

  return (
    <div className="bg-surface border border-line rounded-xl p-5 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-display font-semibold text-content">{player_name}</h3>
          <p className="text-xs text-subtle font-mono mt-0.5">{position}{nfl_team ? ` · ${nfl_team}` : ''}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onRefresh(player_id)}
            title="Re-run analysis"
            className="px-2.5 py-1 text-xs text-subtle hover:text-content bg-raised hover:bg-line rounded-lg border border-line transition-colors"
          >
            ↻
          </button>
          <button
            onClick={() => onUnstar(player_id)}
            title="Unstar player"
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs text-warn hover:brightness-110 bg-warn/10 hover:bg-warn/20 rounded-lg border border-warn/30 transition-all"
          >
            <Star className="size-3 fill-current" />Starred
          </button>
        </div>
      </div>

      {!profile_ready ? (
        <div className="flex items-center gap-3 py-4 text-subtle">
          <div className="w-4 h-4 border-2 border-line border-t-brand rounded-full animate-spin shrink-0" />
          <span className="text-sm">Generating profile... (15-30 sec)</span>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            <StockBadge direction={overall_direction} magnitude={overall_magnitude} />
            <ADPTrendBadge adp_trend={adp_trend} />
            {combined_score != null && (
              <span className="text-xs text-subtle font-mono tabular-nums ml-auto">score {combined_score.toFixed(1)}</span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <ConcernMeter score={concern_level} />
            <SentimentGauge score={sentiment_score} label={sentiment_label} />
          </div>

          {concern_summary && <p className="text-sm text-content/90 leading-relaxed">{concern_summary}</p>}

          {contrarian_flag && (
            <div className="flex items-start gap-2 p-2.5 bg-warn/10 border border-warn/30 rounded-lg">
              <TriangleAlert className="size-3.5 text-warn shrink-0 mt-0.5" />
              <p className="text-xs text-warn/80">Contrarian signal detected.{sentiment_vs_stock ? ` ${sentiment_vs_stock}` : ''}</p>
            </div>
          )}

          {(bullish_factors?.length > 0 || bearish_factors?.length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              <FactorList items={bullish_factors} type="bullish" />
              <FactorList items={bearish_factors} type="bearish" />
            </div>
          )}

          {(short_term_outlook || long_term_outlook) && (
            <div className="grid grid-cols-2 gap-3">
              {short_term_outlook && (
                <div className="bg-raised rounded-lg p-3">
                  <p className="text-xs font-semibold text-subtle uppercase tracking-wide mb-1">Short Term</p>
                  <p className="text-xs text-content/80 leading-snug">{short_term_outlook}</p>
                </div>
              )}
              {long_term_outlook && (
                <div className="bg-raised rounded-lg p-3">
                  <p className="text-xs font-semibold text-subtle uppercase tracking-wide mb-1">Long Term</p>
                  <p className="text-xs text-content/80 leading-snug">{long_term_outlook}</p>
                </div>
              )}
            </div>
          )}

          {draft_recommendation && (
            <div className="bg-brand/10 border border-brand/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-brand mb-0.5">Draft Recommendation</p>
              <p className="text-xs text-content/80 leading-snug">{draft_recommendation}</p>
            </div>
          )}

          {dominant_themes?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {dominant_themes.map((t, i) => (
                <span key={i} className="px-2 py-0.5 bg-raised border border-line rounded text-xs text-subtle">{t}</span>
              ))}
            </div>
          )}

          {historical_context && (
            <details className="group">
              <summary className="text-xs text-subtle/70 hover:text-content cursor-pointer select-none">Historical context</summary>
              <p className="text-xs text-subtle leading-relaxed mt-2 border-t border-line pt-2">{historical_context}</p>
            </details>
          )}

          {last_full_analysis && (
            <p className="text-xs text-subtle/50 font-mono text-right">Updated {relativeTime(last_full_analysis)}</p>
          )}
        </>
      )}
    </div>
  )
}
