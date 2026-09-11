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
    RISING:  { icon: '↑', color: 'text-green-400', bg: 'bg-green-900/30 border-green-800/50' },
    FALLING: { icon: '↓', color: 'text-red-400',   bg: 'bg-red-900/30 border-red-800/50'     },
    STABLE:  { icon: '→', color: 'text-gray-400',  bg: 'bg-gray-800 border-gray-700'          },
  }
  const s = styles[trend] ?? styles.STABLE

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold ${s.bg} ${s.color}`}>
      <span>{s.icon}</span>
      <span>ADP {trend}</span>
      {delta != null && delta !== 0 && (
        <span className="font-mono opacity-70">{delta > 0 ? '+' : ''}{delta.toFixed(1)}</span>
      )}
    </span>
  )
}

function FactorList({ items, type }) {
  if (!items?.length) return null
  const isGood  = type === 'bullish'
  const textCol = isGood ? 'text-green-400' : 'text-red-400'
  const dotCol  = isGood ? 'bg-green-500' : 'bg-red-500'

  return (
    <div>
      <p className={`text-xs font-semibold mb-1.5 ${textCol}`}>
        {isGood ? 'Bullish' : 'Bearish'}
      </p>
      <ul className="flex flex-col gap-1">
        {items.slice(0, 4).map((f, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${dotCol}`} />
            <span className="text-xs text-gray-400 leading-snug">{f}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * TrackerCard — full profile card for a starred player.
 *
 * Props:
 *   player    — tracker card object from GET /api/tracker
 *   onUnstar  — fn(player_id)
 *   onRefresh — fn(player_id)
 */
export default function TrackerCard({ player, onUnstar, onRefresh }) {
  const {
    player_id, player_name, position, nfl_team, profile_ready,
    overall_direction, overall_magnitude,
    concern_level, concern_summary, worry_score, combined_score,
    bullish_factors, bearish_factors,
    sentiment_score, sentiment_label, dominant_themes, contrarian_flag,
    sentiment_vs_stock,
    short_term_outlook, long_term_outlook,
    draft_recommendation,
    adp_trend,
    historical_context,
    last_full_analysis,
  } = player

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-4">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">{player_name}</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {position}{nfl_team ? ` · ${nfl_team}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onRefresh(player_id)}
            title="Re-run analysis"
            className="px-2.5 py-1 text-xs text-gray-500 hover:text-gray-300 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 transition-colors"
          >
            ↻
          </button>
          <button
            onClick={() => onUnstar(player_id)}
            title="Unstar player"
            className="px-2.5 py-1 text-xs text-yellow-500 hover:text-yellow-300 bg-yellow-900/20 hover:bg-yellow-900/30 rounded-lg border border-yellow-800/50 transition-colors"
          >
            ★ Starred
          </button>
        </div>
      </div>

      {/* ── Generating spinner ── */}
      {!profile_ready ? (
        <div className="flex items-center gap-3 py-4 text-gray-500">
          <div className="w-4 h-4 border-2 border-gray-700 border-t-blue-500 rounded-full animate-spin shrink-0" />
          <span className="text-sm">Generating profile… (15-30 sec)</span>
        </div>
      ) : (
        <>
          {/* ── Stock + metrics row ── */}
          <div className="flex items-center gap-3 flex-wrap">
            <StockBadge direction={overall_direction} magnitude={overall_magnitude} />
            <ADPTrendBadge adp_trend={adp_trend} />
            {combined_score != null && (
              <span className="text-xs text-gray-600 font-mono ml-auto">
                score {combined_score.toFixed(1)}
              </span>
            )}
          </div>

          {/* ── Concern + sentiment meters ── */}
          <div className="grid grid-cols-2 gap-4">
            <ConcernMeter score={concern_level} />
            <SentimentGauge score={sentiment_score} label={sentiment_label} />
          </div>

          {/* ── Concern summary ── */}
          {concern_summary && (
            <p className="text-sm text-gray-300 leading-relaxed">{concern_summary}</p>
          )}

          {/* ── Contradiction flag ── */}
          {contrarian_flag && (
            <div className="flex items-start gap-2 p-2.5 bg-yellow-900/20 border border-yellow-800/40 rounded-lg">
              <span className="text-yellow-500 shrink-0">⚠</span>
              <p className="text-xs text-yellow-300/80">
                Contrarian signal detected.{sentiment_vs_stock ? ` ${sentiment_vs_stock}` : ''}
              </p>
            </div>
          )}

          {/* ── Bullish / Bearish factors ── */}
          {(bullish_factors?.length > 0 || bearish_factors?.length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              <FactorList items={bullish_factors} type="bullish" />
              <FactorList items={bearish_factors} type="bearish" />
            </div>
          )}

          {/* ── Short / Long term outlook ── */}
          {(short_term_outlook || long_term_outlook) && (
            <div className="grid grid-cols-2 gap-3">
              {short_term_outlook && (
                <div className="bg-gray-800/60 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-1">Short Term</p>
                  <p className="text-xs text-gray-300 leading-snug">{short_term_outlook}</p>
                </div>
              )}
              {long_term_outlook && (
                <div className="bg-gray-800/60 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-1">Long Term</p>
                  <p className="text-xs text-gray-300 leading-snug">{long_term_outlook}</p>
                </div>
              )}
            </div>
          )}

          {/* ── Draft recommendation ── */}
          {draft_recommendation && (
            <div className="bg-blue-900/20 border border-blue-800/40 rounded-lg p-3">
              <p className="text-xs font-semibold text-blue-400 mb-0.5">Draft Recommendation</p>
              <p className="text-xs text-gray-300 leading-snug">{draft_recommendation}</p>
            </div>
          )}

          {/* ── Dominant themes ── */}
          {dominant_themes?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {dominant_themes.map((t, i) => (
                <span key={i} className="px-2 py-0.5 bg-gray-800 border border-gray-700 rounded text-xs text-gray-400">
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* ── Historical context (collapsed by default) ── */}
          {historical_context && (
            <details className="group">
              <summary className="text-xs text-gray-600 hover:text-gray-400 cursor-pointer select-none">
                Historical context
              </summary>
              <p className="text-xs text-gray-500 leading-relaxed mt-2 border-t border-gray-800 pt-2">
                {historical_context}
              </p>
            </details>
          )}

          {/* ── Footer ── */}
          {last_full_analysis && (
            <p className="text-xs text-gray-700 text-right">
              Updated {relativeTime(last_full_analysis)}
            </p>
          )}
        </>
      )}
    </div>
  )
}
