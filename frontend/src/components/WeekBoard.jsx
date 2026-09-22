import { useEffect, useRef, useState } from 'react'
import { Check, TriangleAlert, ExternalLink } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { REVEAL, slotLabel, tiltHandlers, dotFieldHandlers } from '@/lib/utils'
import { Hint } from '@/components/ui/tooltip'

const PLATFORM = { SLEEPER: 'Sleeper', ESPN: 'ESPN' }
const CARD = 'bg-surface border border-line rounded-xl'
const H2 = 'font-display font-semibold text-2xl text-content'

function untilLabel(iso) {
  if (!iso) return null
  const mins = Math.max(0, Math.round((new Date(iso) - Date.now()) / 60000))
  const d = Math.floor(mins / 1440), h = Math.floor((mins % 1440) / 60), m = mins % 60
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`
}

const kickoffLabel = (iso) =>
  iso ? new Date(iso).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : null

// ── Hero ──────────────────────────────────────────────────────────────────────
export function WeekHero({ data }) {
  const leagues = data.leagues.filter(l => l.win_prob != null)
  const wins = leagues.filter(l => l.win_prob >= 0.5).length
  const avg = data.leagues.length ? data.leagues.reduce((s, l) => s + l.you, 0) / data.leagues.length : null
  const until = untilLabel(data.next_kickoff)
  return (
    <div {...dotFieldHandlers} className={`dot-field ${CARD} px-8 py-9 flex flex-wrap items-end justify-between gap-6 ${REVEAL}`}>
      <div>
        <p className="text-sm text-subtle">Week {data.week}{until ? ` · next kickoff in ${until}` : ''}</p>
        <p className="font-display font-bold text-7xl leading-none tracking-tight text-content mt-1">
          Projected {wins}-{leagues.length - wins}
        </p>
      </div>
      {avg != null && (
        <div className="text-right pb-1">
          <p className="font-display font-semibold text-4xl tabular-nums text-content">{avg.toFixed(1)}</p>
          <p className="text-sm text-subtle">avg projected score per team</p>
        </div>
      )}
    </div>
  )
}

// ── League strip (drag to scroll) ─────────────────────────────────────────────
function Tile({ l, onOpen }) {
  const favored = l.win_prob != null && l.win_prob >= 0.5
  const pct = l.win_prob != null ? Math.round(l.win_prob * 100) : null
  const tone = favored ? 'text-bull' : 'text-bear'
  const status = l.issues ? `${l.issues} to fix` : l.warnings ? `${l.warnings} to check` : 'Lineup set'
  return (
    <button
      type="button"
      onClick={() => onOpen(l)}
      className={`${CARD} shrink-0 w-80 text-left p-5 flex flex-col gap-3 shadow-sm transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 hover:border-content/25`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-sm text-content truncate">{l.name}</span>
        <span className="font-mono text-xs text-subtle shrink-0">{PLATFORM[l.platform]}</span>
      </div>
      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-subtle">You</span>
          <span className={`font-display font-semibold text-3xl tabular-nums ${favored ? 'text-content' : 'text-subtle'}`}>{l.you.toFixed(1)}</span>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-sm text-subtle truncate">{l.opp_name}</span>
          <span className={`font-display font-semibold text-3xl tabular-nums ${favored ? 'text-subtle' : 'text-content'}`}>{l.opp != null ? l.opp.toFixed(1) : '-'}</span>
        </div>
      </div>
      {pct != null && (
        <div className="flex flex-col gap-1.5">
          {/* The yellow tick is the 50% line: the same "line to beat" as Waivers. */}
          <div className="relative h-1.5 rounded-full bg-line">
            <div className={`absolute inset-y-0 left-0 rounded-full ${favored ? 'bg-bull' : 'bg-bear'}`} style={{ width: `${pct}%` }} />
            <div className="absolute left-1/2 -top-1 w-0.5 h-3.5 rounded-sm bg-mark" />
          </div>
          <div className="flex justify-between text-xs">
            <Hint text="Chance to win, from both lineups' projections (Sleeper and ESPN, with your weights). The yellow line marks 50%.">
              <span className={`font-semibold ${tone}`}>{pct}% to win</span>
            </Hint>
            <span className="font-mono text-subtle">{l.record}</span>
          </div>
        </div>
      )}
      <div className={`pt-2.5 border-t border-line text-sm font-medium ${l.issues ? 'text-bear' : l.warnings ? 'text-warn' : 'text-subtle'}`}>
        <Hint text={l.issues ? 'Starters who won\'t play: out, on bye, or an empty slot. Fix these in your league before kickoff.'
          : l.warnings ? 'Starters listed as Questionable or Doubtful. Worth checking before kickoff.'
          : 'Every starter is healthy and playing this week.'}>
          <span className="inline-flex items-center gap-1.5">
            {l.issues || l.warnings ? <TriangleAlert className="size-3.5" /> : <Check className="size-3.5" />}
            {status}
          </span>
        </Hint>
      </div>
    </button>
  )
}

export function LeagueStrip({ leagues, onOpen }) {
  const strip = useRef(null)
  const drag = useRef(null)
  const moved = useRef(false)
  const [dragging, setDragging] = useState(false)
  const [atEnd, setAtEnd] = useState(false)
  const onScroll = () => {
    const el = strip.current
    if (el) setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 2)
  }
  // Also on load and resize: with few leagues nothing overflows, so there's nothing to fade.
  useEffect(() => {
    onScroll()
    window.addEventListener('resize', onScroll)
    return () => window.removeEventListener('resize', onScroll)
  }, [leagues])

  // Click-and-drag scrolling; a real drag swallows the click that follows so letting go
  // over a tile doesn't open it.
  const down = (e) => {
    if (e.button !== 0 || !strip.current) return
    drag.current = { x: e.clientX, left: strip.current.scrollLeft }
    moved.current = false
    setDragging(true)
  }
  const move = (e) => {
    if (!drag.current) return
    const dx = e.clientX - drag.current.x
    if (Math.abs(dx) > 5) moved.current = true
    strip.current.scrollLeft = drag.current.left - dx
  }
  const up = () => { drag.current = null; setDragging(false) }
  const guard = (e) => { if (moved.current) { e.preventDefault(); e.stopPropagation(); moved.current = false } }

  return (
    <section aria-labelledby="leagues" className={`flex flex-col gap-3 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
      <div className="flex items-baseline gap-3">
        <h2 id="leagues" className={H2}>Your leagues</h2>
        <span className="text-sm text-subtle">{leagues.length} matchups this week</span>
        {leagues.length > 3 && <span className="ml-auto text-sm text-subtle">Drag to see more</span>}
      </div>
      <div
        ref={strip}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
        onClickCapture={guard}
        onScroll={onScroll}
        className={`flex gap-4 overflow-x-auto no-scrollbar select-none pb-1 ${atEnd ? '' : 'league-strip'} ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
      >
        {leagues.map(l => <Tile key={`${l.platform}:${l.league_id}`} l={l} onOpen={onOpen} />)}
        {/* Trailing space so the last tile can scroll fully clear of the edge. */}
        <div className="shrink-0 w-4" aria-hidden />
      </div>
    </section>
  )
}

export function LeagueStripSkeleton() {
  return (
    <div className="flex gap-4 overflow-hidden">
      {[0, 1, 2, 3].map(i => (
        <div key={i} className={`${CARD} shrink-0 w-80 p-5 flex flex-col gap-3`}>
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-7 w-full" />
          <Skeleton className="h-7 w-full" />
          <Skeleton className="h-1.5 w-full rounded-full" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  )
}

// ── Needs you ─────────────────────────────────────────────────────────────────
function NeedRow({ n }) {
  const out = n.severity === 'out'
  const when = kickoffLabel(n.kickoff)
  const detail = out
    ? [n.league_name, slotLabel(n.slot), n.swap ? `start ${n.swap.name}${n.swap.proj != null ? ` (${n.swap.proj.toFixed(1)})` : ''}` : 'no healthy backup on your bench'].join(' · ')
    : [when && `plays ${when}`, `in ${n.league_name}`].filter(Boolean).join(' · ')
  return (
    <div className="flex items-center gap-4 px-4 py-3.5 rounded-lg bg-raised">
      <span className={`size-2.5 rounded-full shrink-0 ${out ? 'bg-bear' : 'bg-warn'}`} aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-content">{n.title}</p>
        <p className="text-xs text-subtle mt-0.5 truncate">{detail}</p>
      </div>
      {out && n.url && (
        <a
          href={n.url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 inline-flex items-center gap-1.5 min-h-11 px-4 rounded-lg bg-brand text-brand-fg text-sm font-semibold hover:brightness-110"
        >
          Fix in {PLATFORM[n.platform]} <ExternalLink className="size-3.5" />
        </a>
      )}
    </div>
  )
}

export function NeedsYou({ needs, leagues }) {
  const fixes = needs.filter(n => n.severity === 'out').length
  const set = leagues.filter(l => !l.issues).length
  return (
    <section aria-labelledby="needs" {...tiltHandlers} className={`${CARD} tilt h-full p-6 flex flex-col gap-3.5`}>
      <div className="flex items-baseline gap-2.5">
        <h2 id="needs" className={H2}>Needs you</h2>
        {needs.length > 0 && (
          <span className={`font-mono text-xs font-semibold px-2 py-0.5 rounded-full text-ink ${fixes ? 'bg-bear' : 'bg-warn'}`}>{needs.length}</span>
        )}
        <span className="ml-auto text-sm text-subtle">{set} of {leagues.length} lineups are set</span>
      </div>
      {needs.length ? needs.map((n, i) => <NeedRow key={`${n.league_id}:${n.player_id}:${n.slot}:${i}`} n={n} />) : (
        <p className="flex items-center gap-2 text-sm text-content py-2">
          <Check className="size-4 text-bull" /> All {leagues.length} lineups are set. Nothing to do until kickoff.
        </p>
      )}
    </section>
  )
}

// ── Your Sunday (kickoff windows) ─────────────────────────────────────────────
export function YourSunday({ windows }) {
  const most = Math.max(1, ...windows.map(w => w.count))
  const starters = windows.reduce((s, w) => s + w.count, 0)
  return (
    <section aria-labelledby="sunday" {...tiltHandlers} className={`${CARD} tilt h-full p-6 flex flex-col gap-4`}>
      <div className="flex items-baseline justify-between">
        <h2 id="sunday" className={H2}>When your players play</h2>
        <span className="text-sm text-subtle">{starters} starters</span>
      </div>
      {windows.length ? windows.map(w => (
        <div key={w.kickoff} className={`grid grid-cols-[6.5rem_minmax(0,1fr)_2rem] items-center gap-3 ${w.state === 'post' ? 'opacity-50' : ''}`}>
          <span className="font-mono text-xs text-subtle">{kickoffLabel(w.kickoff)}</span>
          <div className="min-w-0 flex flex-col gap-1.5">
            <div className="h-2.5 rounded-full bg-raised overflow-hidden">
              <div className="h-full rounded-full bg-content/80" style={{ width: `${(w.count / most) * 100}%` }} />
            </div>
            <span className="text-xs text-subtle truncate" title={w.players.join(', ')}>{w.players.join(', ')}</span>
          </div>
          <span className="font-display font-semibold text-xl text-right text-content">{w.count}</span>
        </div>
      )) : <p className="text-sm text-subtle">No games scheduled for your starters this week.</p>}
    </section>
  )
}

// ── Most on the line (players starting in several lineups) ────────────────────
export function MostOnTheLine({ players }) {
  const stacked = players.filter(p => p.starting > 1).slice(0, 4)
  return (
    <section aria-labelledby="exposure" {...tiltHandlers} className={`${CARD} tilt h-full p-6 flex flex-col gap-3`}>
      <div className="flex items-baseline justify-between">
        <h2 id="exposure" className={H2}>Most on the line</h2>
        <span className="text-sm text-subtle">starting in 2+ lineups</span>
      </div>
      {stacked.length ? stacked.map(p => (
        <div key={p.player_id} className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-content truncate">{p.name} <span className="font-mono text-xs text-subtle">{p.position}</span></p>
            <p className="text-xs text-subtle truncate">{p.leagues.filter(l => l.is_starter).map(l => l.name).join(', ')}</p>
          </div>
          <span className="font-display font-semibold text-xl text-content shrink-0">{p.starting}<span className="text-sm text-subtle font-sans font-normal"> lineups</span></span>
        </div>
      )) : <p className="text-sm text-subtle">No one starts for you in more than one league, so one bad game only hurts one team.</p>}
    </section>
  )
}
