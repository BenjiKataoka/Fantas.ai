import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { getWaivers, analyzeFreeAgent, starPlayer } from '../services/api'
import PlayerAvatar from '../components/PlayerAvatar'
import TeamAccent from '../components/TeamAccent'
import InjuryBadge from '../components/InjuryBadge'
import { WaiverSkeleton } from '../components/Skeletons'
import Notice from '../components/Notice'
import { REVEAL, slotLabel, tiltHandlers } from '@/lib/utils'
import { TrendingDown, Star } from 'lucide-react'
import { toast } from 'sonner'
import CollapseRow from '../components/CollapseRow'
import { LoadingDots } from '../components/Spinner'
import { Hint } from '@/components/ui/tooltip'
import Num from '../components/Num'

const FILTERS = ['All', 'QB', 'RB', 'WR', 'TE', 'K']
const POS_COLORS = { QB: 'text-pos-qb', RB: 'text-pos-rb', WR: 'text-pos-wr', TE: 'text-pos-te' }
const ALL_LIMIT = 25

function compact(n) {
  if (n == null) return '-'
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n)
}

function Trend({ p }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <Num className="text-subtle text-xs"><span className="text-bull">+{compact(p.adds)}</span> / <span className="text-bear">-{compact(p.drops)}</span></Num>
      {p.being_dropped && (
        <Hint text="More managers dropped him than added him in the last 24 hours, usually a sign of bad news.">
          <span className="flex items-center gap-1 text-xs text-bear mt-0.5"><TrendingDown className="size-3" />Being dropped</span>
        </Hint>
      )}
    </div>
  )
}

// Only news that changes a pickup decision. General recaps still reach the Analyze prompt.
const USEFUL_NEWS = new Set(['INJURY', 'TRANSACTION', 'DEPTH_CHART', 'CONTRACT'])

function Headline({ news }) {
  if (!news || !USEFUL_NEWS.has(news.news_type)) return null
  return (
    <a href={news.source_url || undefined} target="_blank" rel="noreferrer"
       className={`block text-xs line-clamp-2 mt-0.5 hover:underline ${news.news_type === 'INJURY' ? 'text-warn' : 'text-subtle'}`}
       title={news.headline}>
      {news.headline}
    </a>
  )
}

const VERDICT = {
  ADD:   { label: 'Add now', cls: 'bg-bull/10 border-bull/30 text-bull' },
  STASH: { label: 'Stash',   cls: 'bg-warn/10 border-warn/30 text-warn' },
  PASS:  { label: 'Pass',    cls: 'bg-raised border-line text-subtle' },
}

function Verdict({ p, a }) {
  const v = VERDICT[a.verdict]
  const watch = async () => {
    try {
      const res = await starPlayer(p.player_id)
      if (res.data.status === 'already_starred') toast(`${p.name} is already on your watchlist.`)
      else if (res.data.status === 'error') toast.error(res.data.detail || `Couldn't watch ${p.name}.`)
      else toast.success(`Watching ${p.name}. He's on your Tracker now.`)
    } catch (err) {
      toast.error(err.response?.data?.detail || `Couldn't watch ${p.name}.`)
    }
  }
  return (
    <div className="px-5 py-4 flex flex-wrap items-start gap-x-6 gap-y-3">
      <span className={`shrink-0 px-2 py-1 rounded border text-sm font-semibold ${v.cls}`}>{v.label}</span>
      <div className="flex-1 min-w-64 text-sm">
        <ul className="space-y-1 text-content/90 list-disc pl-4">{a.reasons.map(r => <li key={r}>{r}</li>)}</ul>
        {a.risk && <p className="mt-2 text-subtle"><span className="text-warn">Risk:</span> {a.risk}</p>}
        <p className="mt-2 text-xs text-subtle">
          {p.replaces ? <>Projects <span className="text-bull font-mono">+{p.upgrade.toFixed(1)}</span> a week over {p.replaces.name}.</>
            : p.upgrade > 0 ? <>Fills an empty lineup spot, <span className="text-bull font-mono">+{p.upgrade.toFixed(1)}</span> a week.</>
            : "Doesn't project higher than any of your starters."}
        </p>
      </div>
      <button onClick={watch} className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm text-subtle border border-line hover:text-content hover:bg-raised">
        <Star className="size-3.5" />Watch
      </button>
    </div>
  )
}

// lineAbove: this row's top border becomes the TV first-down line. Free agents above it
// would start for you, everyone below is depth. Drawn on the border so there's one rule.
function Row({ p, i, analysis, open, onAnalyze, lineAbove }) {
  return (
    <>
    <tr className={`${lineAbove ? 'border-t-2 border-mark' : 'border-t border-line/50'} ${REVEAL}`} style={{ animationDelay: `${140 + Math.min(i, 8) * 45}ms` }}>
      <td className="relative px-3 py-2.5">
        {lineAbove && (
          <span className="absolute left-3 top-0 -translate-y-1/2 px-1.5 py-px rounded-sm bg-mark text-mark-fg text-[11px] font-semibold whitespace-nowrap">
            Line to beat: above it would start for you
          </span>
        )}
        <div className="flex items-center gap-2.5 min-w-0">
          <TeamAccent team={p.nfl_team} />
          <PlayerAvatar playerId={p.player_id} name={p.name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-content truncate">{p.name}</span>
              <span title={p.injury_body_part || undefined}><InjuryBadge status={p.injury_status} /></span>
              <span className="text-xs text-subtle font-mono">{p.nfl_team || 'FA'}</span>
            </div>
            <Headline news={p.news} />
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5">
        <span className={`font-mono text-xs font-semibold ${POS_COLORS[p.position] || 'text-subtle'}`}>{p.position}</span>
      </td>
      <td className="px-3 py-2.5 text-right"><Num className="text-subtle">{p.week_proj.toFixed(1)}</Num></td>
      <td className="px-3 py-2.5 text-right"><Num className="text-content font-medium">{p.proj.toFixed(1)}</Num></td>
      <td className="px-3 py-2.5 text-right"><Num className="text-subtle">{p.percent_rostered != null ? `${p.percent_rostered}%` : '-'}</Num></td>
      <td className="px-3 py-2.5 text-right"><Trend p={p} /></td>
      <td className="px-3 py-2.5 pl-5">
        {/* Fills the cell so Analyze, Hide and the loading dots all occupy the same
            box; the column is fixed-width, so a wider label would spill out of it. */}
        <button
          onClick={onAnalyze}
          disabled={analysis?.loading}
          aria-expanded={open}
          aria-busy={analysis?.loading || undefined}
          aria-label={analysis?.loading ? `Analyzing ${p.name}` : undefined}
          className={`w-full inline-flex items-center justify-center px-2.5 py-1 rounded-md text-xs font-medium leading-4 border transition-colors disabled:opacity-60 ${
            open ? 'border-brand text-brand' : 'border-line text-subtle hover:text-content hover:bg-raised'}`}
        >
          {/* h-4 matches the text line box, so the button keeps its height while loading. */}
          {analysis?.loading ? <span className="inline-flex h-4 items-center"><LoadingDots /></span> : open ? 'Hide' : 'Analyze'}
        </button>
      </td>
    </tr>
    <CollapseRow open={open} colSpan={7}>
      {analysis?.data && <Verdict p={p} a={analysis.data} />}
    </CollapseRow>
    </>
  )
}

const SLOT_ORDER = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'WRRB_FLEX', 'REC_FLEX', 'SUPER_FLEX', 'K', 'DEF']
const CARD = 'bg-surface border border-line rounded-xl tilt p-4'

function LineToBeat({ lineup, weeks }) {
  const rows = [...lineup].sort((a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot))
  return (
    <div {...tiltHandlers} className={CARD}>
      <h2 className="font-display font-semibold text-content">Your starters</h2>
      <p className="text-xs text-subtle mt-0.5 mb-3">Points per week, next {weeks}. A pickup has to beat these.</p>
      <ul className="space-y-1.5 text-sm">
        {rows.map(r => (
          <li key={`${r.slot}-${r.name}`} className="flex items-baseline gap-2">
            <span className="w-11 shrink-0 font-mono text-xs text-subtle">{slotLabel(r.slot)}</span>
            <span className="flex-1 truncate text-content/90">{r.name}</span>
            <Num className="text-subtle">{r.proj.toFixed(1)}</Num>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Legend({ weeks }) {
  const items = [
    ['This wk', 'Sleeper and ESPN blended with your weights.'],
    [`Next ${weeks.length}`, `Points per week over the next ${weeks.length} weeks. Injured weeks count as zero.`],
    ['Rostered', "ESPN's league-wide %."],
    ['Adds / drops', "Sleeper, last 24 hours."],
  ]
  return (
    <dl className="px-1 space-y-2 text-xs">
      {items.map(([k, v]) => (
        <div key={k}><dt className="inline text-content/80 font-medium">{k}: </dt><dd className="inline text-subtle">{v}</dd></div>
      ))}
    </dl>
  )
}

export default function Waivers() {
  const { credentials, rosterData } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('All')
  const [analyses, setAnalyses] = useState({})   // player_id → { loading, data }
  const [openId, setOpenId] = useState(null)
  const leagueId = credentials?.leagueId

  const analyze = async (p) => {
    if (analyses[p.player_id]?.data) return setOpenId(id => (id === p.player_id ? null : p.player_id))
    setAnalyses(a => ({ ...a, [p.player_id]: { loading: true } }))
    try {
      const res = await analyzeFreeAgent(p.player_id, credentials.username, leagueId, credentials.platform)
      setAnalyses(a => ({ ...a, [p.player_id]: { data: res.data } }))
      setOpenId(p.player_id)
      if (!res.data.cached && res.data.remaining <= 3) toast(`${res.data.remaining} analyses left today.`)
    } catch (err) {
      setAnalyses(a => ({ ...a, [p.player_id]: undefined }))
      toast.error(err.response?.data?.detail || `Couldn't analyze ${p.name}.`)
    }
  }

  useEffect(() => {
    if (!credentials || !leagueId) return
    let cancelled = false
    setError(null); setData(null); setAnalyses({}); setOpenId(null)
    getWaivers(credentials.username, leagueId, credentials.platform)
      .then(res => { if (!cancelled) setData(res.data) })
      .catch(err => { if (!cancelled) setError(err.response?.data?.detail || 'Could not load the waiver wire.') })
    return () => { cancelled = true }
  }, [credentials, leagueId])

  if (!credentials) return <Notice title="No league yet" message="Pick a league on the Dashboard and the waiver wire fills in." actionLabel="Go to the Dashboard" to="/" />
  if (rosterData?.season_type === 'off') return <Notice title="The waiver wire opens once the season does." message="Free agents are ranked against your lineup, so it needs weekly projections." />

  const all = data?.candidates || []
  const rows = filter === 'All' ? all.slice(0, ALL_LIMIT) : all.filter(p => p.position === filter)
  const starters = all.filter(p => p.upgrade > 0).length
  // Rows are sorted by upgrade first, so the line sits before the first non-upgrade row.
  const firstDepth = rows.findIndex(p => !(p.upgrade > 0))
  const lineAt = firstDepth > 0 ? firstDepth : -1

  return (
    <div className="max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-display font-bold text-content">Waiver wire{data ? `, Week ${data.week}` : ''}</h1>
          {data?.league_name && <p className="text-sm text-subtle mt-0.5">{data.league_name}</p>}
        </div>
        <div className="flex gap-1">
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-md text-sm font-mono ${f === filter ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content hover:bg-raised'}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {error && <Notice tone="error" title={error} actionLabel="Try again" onAction={() => window.location.reload()} />}
      {!data && !error && <WaiverSkeleton />}

      {data && (
        <div className="flex flex-col gap-6">
          <div className={REVEAL}>
            <p className="text-lg leading-relaxed text-content/90 max-w-2xl">
              {starters === 0
                ? `Nobody available outscores your starters over the next ${data.horizon_weeks.length} weeks. The list below is depth, sorted by projection.`
                : `${starters === 1 ? 'One free agent outscores' : `${starters} free agents outscore`} one of your starters over the next ${data.horizon_weeks.length} weeks.`}
            </p>
            {data.warning && <p className="text-sm text-warn mt-2">{data.warning}</p>}
          </div>

          <div className="flex flex-col xl:flex-row gap-6 items-start">
            <div key={filter} className={`w-fit max-w-full overflow-x-auto bg-surface border border-line rounded-xl shadow-sm ${REVEAL}`} style={{ animationDelay: '90ms' }}>
              {/* Every column is fixed and the table is exactly their sum (51.5rem), so a long
                  headline wraps inside Player instead of stretching the row. */}
              <table className="w-[51.5rem] table-fixed text-sm">
                <colgroup>
                  <col className="w-72" /><col className="w-14" /><col className="w-20" /><col className="w-20" />
                  <col className="w-20" /><col className="w-32" /><col className="w-28" />
                </colgroup>
                <thead>
                  <tr className="text-subtle text-xs whitespace-nowrap">
                    <th className="px-3 py-2.5 text-left font-medium">Player</th>
                    <th className="px-3 py-2.5 text-left font-medium">Pos</th>
                    <th className="px-3 py-2.5 text-right font-medium">This wk</th>
                    <th className="px-3 py-2.5 text-right font-medium">Next {data.horizon_weeks.length}</th>
                    <th className="px-3 py-2.5 text-right font-medium">Rostered</th>
                    <th className="px-3 py-2.5 text-right font-medium">Adds / drops</th>
                    <th className="px-3 py-2.5"><span className="sr-only">Analyze</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p, i) => <Row key={p.player_id} p={p} i={i} lineAbove={i === lineAt} analysis={analyses[p.player_id]} open={openId === p.player_id} onAnalyze={() => analyze(p)} />)}
                  {!rows.length && (
                    <tr><td colSpan={7} className="px-3 py-8 text-center text-subtle">No free agents at {filter} are projected to score this week.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <aside className={`w-full xl:w-72 shrink-0 flex flex-col gap-4 ${REVEAL}`} style={{ animationDelay: '180ms' }}>
              <LineToBeat lineup={data.lineup} weeks={data.horizon_weeks.length} />
              <Legend weeks={data.horizon_weeks} />
            </aside>
          </div>
        </div>
      )}
    </div>
  )
}
