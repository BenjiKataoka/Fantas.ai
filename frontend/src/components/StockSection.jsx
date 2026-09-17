import ConcernMeter from './ConcernMeter'
import SentimentGauge from './SentimentGauge'
import StockBadge from './StockBadge'

// Relative "analyzed 3h ago" from an ISO timestamp.
function timeAgo(iso) {
  if (!iso) return null
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function FactorList({ label, items, tone }) {
  if (!items?.length) return null
  const dot = tone === 'bull' ? 'bg-bull' : 'bg-bear'
  return (
    <div className="flex-1 min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-subtle mb-1.5">{label}</div>
      <ul className="flex flex-col gap-1">
        {items.map((f, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs text-content/80 leading-snug">
            <span className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${dot}`} />
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * StockSection — the current-sentiment dropdown for a roster row.
 * `stock` is the serialized player_stock_profile (or null if never analyzed).
 */
export default function StockSection({ stock }) {
  if (!stock) {
    return (
      <div className="px-4 py-5 text-center">
        <p className="text-sm text-subtle">Not analyzed yet.</p>
        <p className="text-xs text-subtle/60 mt-1">
          Run <span className="text-content font-medium">Analyze my roster</span> to generate a stock &amp; sentiment profile.
        </p>
      </div>
    )
  }

  const {
    overall_direction, overall_magnitude, concern_level, concern_summary,
    sentiment_score, sentiment_label, bullish_factors, bearish_factors,
    short_term_outlook, long_term_outlook, dominant_themes, contrarian_flag,
    last_full_analysis,
  } = stock

  // A transient failure on the scoring passes can leave these null. Show a clear notice
  // instead of a blank meter area — it self-repairs on the next analysis.
  const scoringIncomplete = concern_level == null && sentiment_score == null

  return (
    <div className="px-4 py-4 flex flex-col gap-4">
      {/* Header: overall stock + freshness */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-subtle font-display">Stock &amp; Sentiment</span>
          {overall_direction && <StockBadge direction={overall_direction} magnitude={overall_magnitude} size="sm" />}
          {contrarian_flag && (
            <span className="px-1.5 py-0.5 rounded border border-warn/30 bg-warn/10 text-warn text-[10px] font-semibold uppercase tracking-wide">
              Contrarian
            </span>
          )}
        </div>
        {last_full_analysis && (
          <span className="text-[11px] text-subtle/60 font-mono shrink-0">analyzed {timeAgo(last_full_analysis)}</span>
        )}
      </div>

      {/* Meters — or a notice if the scoring passes didn't complete */}
      {scoringIncomplete ? (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-warn/10 border border-warn/30 text-xs text-content/80">
          <span className="text-warn">⚠</span>
          Sentiment scoring didn’t finish for this player — it’ll retry on the next analysis.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ConcernMeter score={concern_level} />
          <SentimentGauge score={sentiment_score} label={sentiment_label} />
        </div>
      )}

      {concern_summary && (
        <p className="text-sm text-content/90 leading-relaxed border-l-2 border-line pl-3">{concern_summary}</p>
      )}

      {/* Bull / bear factors */}
      {(bullish_factors?.length || bearish_factors?.length) ? (
        <div className="flex gap-6">
          <FactorList label="Bullish" items={bullish_factors} tone="bull" />
          <FactorList label="Bearish" items={bearish_factors} tone="bear" />
        </div>
      ) : null}

      {/* Outlook */}
      {(short_term_outlook || long_term_outlook) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
          {short_term_outlook && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-subtle mb-0.5">Short term</div>
              <p className="text-content/80 leading-snug">{short_term_outlook}</p>
            </div>
          )}
          {long_term_outlook && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-subtle mb-0.5">Long term</div>
              <p className="text-content/80 leading-snug">{long_term_outlook}</p>
            </div>
          )}
        </div>
      )}

      {/* Themes */}
      {dominant_themes?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {dominant_themes.map((t, i) => (
            <span key={i} className="px-2 py-0.5 rounded-full bg-raised border border-line text-[11px] text-subtle">{t}</span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
