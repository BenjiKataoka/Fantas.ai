import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, TriangleAlert, ExternalLink } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { REVEAL, slotLabel, tiltHandlers, dotFieldHandlers } from '@/lib/utils'
import { Hint } from '@/components/ui/tooltip'
import CountUp from './CountUp'

const PLATFORM = { SLEEPER: 'Sleeper', ESPN: 'ESPN' }
const PLATFORM_LOGO = { SLEEPER: '/platform/sleeper.png', ESPN: '/platform/espn.png' }

// A league or team image that simply disappears if the platform won't serve it.
function Logo({ src, alt, className }) {
  const [ok, setOk] = useState(true)
  if (!src || !ok) return null
  return <img src={src} alt={alt} onError={() => setOk(false)} className={className} loading="lazy" />
}

// The platform's mark filling the whole tile, faint enough to read as texture.
function Watermark({ platform }) {
  return (
    <img
      src={PLATFORM_LOGO[platform]}
      alt=""
      aria-hidden
      className="pointer-events-none select-none absolute inset-0 m-auto h-full w-auto max-w-none opacity-[0.07] dark:opacity-[0.09]"
    />
  )
}
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
// "This week" / "Last week" switch shown in either hero.
export function ModeToggle({ mode, onChange }) {
  const opt = (value, label) => (
    <button
      type="button"
      onClick={() => onChange(value)}
      aria-pressed={mode === value}
      className={`px-3 py-1 rounded-md text-sm font-medium ${mode === value ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content'}`}
    >
      {label}
    </button>
  )
  return <div className="inline-flex gap-1 p-1 rounded-lg bg-raised/80 border border-line">{opt('this', 'This week')}{opt('last', 'Last week')}</div>
}

function HeroCard({ eyebrow, title, stat, statLabel, statTone = 'text-content', toggle }) {
  return (
    <div {...dotFieldHandlers} className={`dot-field ${CARD} px-8 py-8 flex flex-col gap-5 ${REVEAL}`}>
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-subtle">{eyebrow}</p>
        {toggle}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <p className="font-display font-bold text-7xl leading-none tracking-tight text-content">{title}</p>
        {stat != null && (
          <div className="text-right pb-1">
            <p className={`font-display font-semibold text-4xl tabular-nums ${statTone}`}>{stat}</p>
            <p className="text-sm text-subtle">{statLabel}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export function ResultsHero({ data, toggle }) {
  const r = data.record || { wins: 0, losses: 0, ties: 0 }
  return (
    <HeroCard
      eyebrow={`Week ${data.week} final`}
      title={`You went ${r.wins}-${r.losses}${r.ties ? `-${r.ties}` : ''}`}
      stat={data.left_on_bench.toFixed(1)}
      statLabel="points left on your benches"
      statTone={data.left_on_bench >= 10 ? 'text-bear' : 'text-content'}
      toggle={toggle}
    />
  )
}

export function WeekHero({ data, toggle }) {
  const leagues = data.leagues.filter(l => l.win_prob != null)
  const wins = leagues.filter(l => l.win_prob >= 0.5).length
  const avg = data.leagues.length ? data.leagues.reduce((s, l) => s + l.you, 0) / data.leagues.length : null
  const until = untilLabel(data.next_kickoff)
  return (
    <HeroCard
      eyebrow={`Week ${data.week}${until ? ` · next kickoff in ${until}` : ''}`}
      title={`Projected ${wins}-${leagues.length - wins}`}
      stat={avg != null ? avg.toFixed(1) : null}
      statLabel="avg projected score per team"
      toggle={toggle}
    />
  )
}

// ── League strip (drag to scroll) ─────────────────────────────────────────────
export function Tile({ l, onOpen }) {
  const favored = l.win_prob != null && l.win_prob >= 0.5
  const pct = l.win_prob != null ? Math.round(l.win_prob * 100) : null
  const tone = favored ? 'text-bull' : 'text-bear'
  const status = l.issues ? `${l.issues} to fix` : l.warnings ? `${l.warnings} to check` : 'Lineup set'
  return (
    <button
      type="button"
      onClick={() => onOpen(l)}
      className={`${CARD} relative overflow-hidden shrink-0 w-80 text-left p-5 flex flex-col gap-3 shadow-sm transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 hover:border-content/25`}
    >
      <Watermark platform={l.platform} />
      <div className="relative flex items-center justify-between gap-2">
        <span className="font-semibold text-sm text-content truncate">
          {l.name}<span className="sr-only"> on {PLATFORM[l.platform]}</span>
        </span>
        {l.live && (
          <Hint text="Scores are live: players whose games have started count their real points, the rest still show projections.">
            <span className="shrink-0 inline-flex items-center gap-1.5 text-xs font-semibold text-bull">
              <span className="live-blink size-2 rounded-full bg-bear" aria-hidden />Live
            </span>
          </Hint>
        )}
      </div>
      <div className="relative">
        <div className="flex items-baseline justify-between gap-3">
          <span className="flex items-center gap-2 text-sm text-subtle truncate">
            <Logo src={l.my_logo} alt="" className="size-5 rounded-full bg-raised object-cover" />
            {l.my_name || 'You'}
          </span>
          <span className={`font-display font-semibold text-3xl tabular-nums ${favored ? 'text-content' : 'text-subtle'}`}><CountUp value={l.you} /></span>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <span className="flex items-center gap-2 text-sm text-subtle truncate">
            <Logo src={l.opp_logo} alt="" className="size-5 rounded-full bg-raised object-cover" />
            {l.opp_name}
          </span>
          <span className={`font-display font-semibold text-3xl tabular-nums ${favored ? 'text-subtle' : 'text-content'}`}><CountUp value={l.opp} /></span>
        </div>
      </div>
      {pct != null && (
        <div className="relative flex flex-col gap-1.5">
          {/* The yellow tick is the 50% line: the same "line to beat" as Waivers. */}
          <div className="relative h-1.5 rounded-full bg-line">
            <div className={`absolute inset-y-0 left-0 rounded-full ${favored ? 'bg-bull' : 'bg-bear'}`} style={{ width: `${pct}%` }} />
            <div className="absolute left-1/2 -top-1 w-0.5 h-3.5 rounded-sm bg-mark" />
          </div>
          <div className="flex justify-between text-xs">
            <Hint text={l.live
              ? "Chance to win from the live score plus what's left to play. It tightens as games finish."
              : "Chance to win, from both lineups' projections (Sleeper and ESPN, with your weights). The yellow line marks 50%."}>
              <span className={`font-semibold ${tone}`}>{pct}% to win</span>
            </Hint>
            <span className="font-mono text-subtle">
              {l.live && l.progress ? `${l.progress.played} of ${l.progress.total} played` : l.record}
            </span>
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

// A finished week's tile: result, final score, and what the bench left behind.
export function ResultTile({ r, onOpen }) {
  const chip = r.result === 'W' ? 'bg-bull' : r.result === 'L' ? 'bg-bear' : 'bg-subtle'
  return (
    <button
      type="button"
      onClick={() => onOpen(r)}
      className={`${CARD} relative overflow-hidden shrink-0 w-80 text-left p-5 flex flex-col gap-3 shadow-sm transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 hover:border-content/25`}
    >
      <Watermark platform={r.platform} />
      <div className="relative flex items-center justify-between gap-2">
        <span className="font-semibold text-sm text-content truncate">
          {r.name}<span className="sr-only"> on {PLATFORM[r.platform]}</span>
        </span>
        {r.result && <span className={`font-display font-bold text-sm px-2 py-0.5 rounded text-ink ${chip}`}>{r.result}</span>}
      </div>
      <div className="relative flex items-baseline gap-2.5">
        <span className="font-display font-bold text-4xl tabular-nums text-content"><CountUp value={r.you} /></span>
        <span className="text-sm text-subtle">to</span>
        <span className="font-display font-semibold text-2xl tabular-nums text-subtle"><CountUp value={r.opp} /></span>
      </div>
      <p className="relative flex items-center gap-2 text-sm text-subtle truncate -mt-2">
        <Logo src={r.opp_logo} alt="" className="size-5 rounded-full bg-raised object-cover" />
        vs {r.opp_name}
      </p>
      <div className="relative flex justify-between pt-2.5 border-t border-line text-sm">
        <Hint text="Points your best possible lineup would have added. It compares what your bench actually scored with who you started.">
          <span className="text-subtle">Left on bench</span>
        </Hint>
        <span className={`font-mono font-semibold ${r.left_on_bench >= 10 ? 'text-bear' : 'text-subtle'}`}>{r.left_on_bench.toFixed(1)}</span>
      </div>
    </button>
  )
}

export function LeagueStrip({ subtitle, count, children }) {
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
  }, [count])

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
  // Releasing outside the strip has to end the drag too, or it stays "held".
  useEffect(() => {
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    return () => {
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
  }, [])
  const guard = (e) => { if (moved.current) { e.preventDefault(); e.stopPropagation(); moved.current = false } }

  return (
    <section aria-labelledby="leagues" className={`flex flex-col gap-3 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
      <div className="flex items-baseline gap-3">
        <h2 id="leagues" className={H2}>Your leagues</h2>
        <span className="text-sm text-subtle">{subtitle}</span>
        {count > 3 && <span className="ml-auto text-sm text-subtle">Drag to see more</span>}
      </div>
      {/* overflow-x clips vertically too, so py-2 gives the tiles' hover lift room to live in. */}
      <div
        ref={strip}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
        onClickCapture={guard}
        onScroll={onScroll}
        className={`flex gap-4 overflow-x-auto no-scrollbar select-none py-2 ${atEnd ? '' : 'league-strip'} ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
      >
        {children}
        {/* Trailing space so the last tile can scroll fully clear of the edge. */}
        <div className="shrink-0 w-4" aria-hidden />
      </div>
    </section>
  )
}

function LeagueStripSkeleton() {
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

// One bento card's frame: heading, an optional right-hand meta line, then its rows.
function CardSkeleton({ span, titleW, metaW, children }) {
  return (
    <section className={`${CARD} h-full p-6 flex flex-col gap-3 ${span || ''}`}>
      <div className="flex items-baseline gap-2.5">
        <Skeleton className={`h-7 ${titleW}`} />
        {metaW && <Skeleton className={`h-3.5 ml-auto ${metaW}`} />}
      </div>
      {children}
    </section>
  )
}

// A raised row carrying two lines and either a Fix button or a score.
function StackRow({ dot, action }) {
  return (
    <div className="flex items-center gap-4 px-4 py-3.5 rounded-lg bg-raised">
      {dot && <Skeleton className="size-2.5 rounded-full shrink-0" />}
      <div className="flex-1 min-w-0 space-y-1.5">
        <Skeleton className="h-3.5 w-48 max-w-full" />
        <Skeleton className="h-2.5 w-60 max-w-full" />
      </div>
      <Skeleton className={action ? 'h-11 w-32 rounded-lg shrink-0' : 'h-6 w-12 shrink-0'} />
    </div>
  )
}

// The pickup rows alone: the card around them is already on screen while they load.
function PickupsSkeleton({ rows = 3 }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1.5 pb-3 border-b border-line last:border-0">
          <div className="flex items-baseline justify-between gap-3">
            <Skeleton className="h-3.5 w-36" />
            <Skeleton className="h-3 w-16 shrink-0" />
          </div>
          <Skeleton className="h-2.5 w-44 max-w-full" />
        </div>
      ))}
    </>
  )
}

// The whole board while it loads: hero, league tiles, and every bento card that
// follows, so the page keeps its shape instead of growing a card at a time.
export function BoardSkeleton({ mode = 'this' }) {
  const three = [0, 1, 2]
  return (
    <>
      <div className={`${CARD} px-8 py-8 flex flex-col gap-5`}>
        <div className="flex items-center justify-between gap-4">
          <Skeleton className="h-3.5 w-52 max-w-[50%]" />
          <Skeleton className="h-9 w-48 rounded-lg shrink-0" />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Skeleton className="h-16 w-72 max-w-full" />
          <div className="flex flex-col items-end gap-2 pb-1">
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-3.5 w-48 max-w-full" />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-baseline gap-3">
          <Skeleton className="h-7 w-36" />
          <Skeleton className="h-3.5 w-40" />
        </div>
        <LeagueStripSkeleton />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {mode === 'last' ? (
          <>
            <CardSkeleton span="lg:col-span-2" titleW="w-72 max-w-full">
              {three.map(i => <StackRow key={i} />)}
            </CardSkeleton>
            <CardSkeleton titleW="w-48">
              <Skeleton className="h-3.5 w-56 max-w-full -mt-1" />
              <PickupsSkeleton />
              <Skeleton className="h-11 w-44 rounded-lg mt-auto" />
            </CardSkeleton>
          </>
        ) : (
          <>
            <CardSkeleton span="lg:col-span-2" titleW="w-36" metaW="w-40">
              {three.map(i => <StackRow key={i} dot action />)}
            </CardSkeleton>
            <CardSkeleton titleW="w-52" metaW="w-16">
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="grid grid-cols-[6.5rem_minmax(0,1fr)_2rem] items-center gap-3">
                  <Skeleton className="h-3 w-20" />
                  <div className="min-w-0 flex flex-col gap-1.5">
                    <Skeleton className="h-2.5 rounded-full" style={{ width: `${100 - i * 18}%` }} />
                    <Skeleton className="h-2.5 w-full" />
                  </div>
                  <Skeleton className="h-5 w-6 ml-auto" />
                </div>
              ))}
            </CardSkeleton>
            <CardSkeleton span="lg:col-span-2" titleW="w-24">
              {three.map(i => (
                <div key={i} className="flex items-start gap-3 py-1">
                  <Skeleton className="size-9 rounded-full shrink-0" />
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <Skeleton className="h-3.5 w-3/4" />
                    <Skeleton className="h-2.5 w-1/3" />
                  </div>
                  <Skeleton className="h-5 w-16 rounded shrink-0" />
                </div>
              ))}
            </CardSkeleton>
            <CardSkeleton titleW="w-44" metaW="w-32">
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <Skeleton className="h-3.5 w-36 max-w-full" />
                    <Skeleton className="h-2.5 w-44 max-w-full" />
                  </div>
                  <Skeleton className="h-5 w-20 shrink-0" />
                </div>
              ))}
            </CardSkeleton>
          </>
        )}
      </div>
    </>
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

// ── Results mode cards ────────────────────────────────────────────────────────
export function BenchMisses({ misses }) {
  return (
    <section aria-labelledby="misses" {...tiltHandlers} className={`${CARD} tilt h-full p-6 flex flex-col gap-3`}>
      <h2 id="misses" className={H2}>Points that sat on your bench</h2>
      {misses.length ? misses.map(m => (
        <div key={`${m.league_name}:${m.player_id}`} className="flex items-center gap-4 px-4 py-3 rounded-lg bg-raised">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-content">{m.name} scored {m.points.toFixed(1)} on your bench</p>
            <p className="text-xs text-subtle mt-0.5 truncate">{m.league_name} · {m.position}</p>
          </div>
          <span className="font-display font-semibold text-2xl text-bear shrink-0">{m.points.toFixed(1)}</span>
        </div>
      )) : (
        <p className="flex items-center gap-2 text-sm text-content py-2">
          <Check className="size-4 text-bull" /> You started the right players everywhere.
        </p>
      )}
    </section>
  )
}

export function Pickups({ pickups, loading }) {
  return (
    <section aria-labelledby="pickups" {...tiltHandlers} className={`${CARD} tilt h-full p-6 flex flex-col gap-3`}>
      <h2 id="pickups" className={H2}>Before waivers run</h2>
      <p className="text-sm text-subtle -mt-1">Free agents who would start for you, and where.</p>
      {loading ? <PickupsSkeleton /> : pickups.length ? pickups.map(p => (
        <div key={p.player_id} className="flex flex-col gap-0.5 pb-3 border-b border-line last:border-0">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-medium text-content truncate">{p.name}, {p.position}</span>
            <span className="font-mono text-xs font-semibold text-bull shrink-0">+{p.upgrade.toFixed(1)} / wk</span>
          </div>
          <span className="text-xs text-subtle truncate">Would start in {p.leagues.join(', ')}</span>
        </div>
      )) : <p className="text-sm text-subtle">No free agent beats your current starters in any league right now.</p>}
      <Link to="/waivers" className="mt-auto self-start inline-flex items-center min-h-11 px-4 rounded-lg bg-brand text-brand-fg text-sm font-semibold hover:brightness-110">
        Open the waiver wire
      </Link>
    </section>
  )
}
