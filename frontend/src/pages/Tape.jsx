import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, Play, Star } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { getTape } from '../services/api'
import { REVEAL, tiltHandlers } from '@/lib/utils'
import { teamAccent } from '@/lib/teams'
import { useTheme } from '@/lib/theme'
import { Hint } from '@/components/ui/tooltip'
import Notice from '../components/Notice'
import { Skeleton } from '@/components/ui/skeleton'

const CARD = 'bg-surface border border-line rounded-xl'
const H2 = 'font-display font-semibold text-xl text-content'
const POS_COLORS = { QB: 'text-pos-qb', RB: 'text-pos-rb', WR: 'text-pos-wr', TE: 'text-pos-te', K: 'text-subtle' }

// Embeds are heavy, so nothing loads a player until it is the one being watched:
// the rest of the page is thumbnails. nocookie keeps YouTube from setting tracking
// cookies on a viewer who never presses play.
function Theater({ video, subtitle }) {
  if (!video) return null
  const watchUrl = `https://www.youtube.com/watch?v=${video.video_id}`
  // The NFL blocks embedded playback on everything except its weekly compilations, so
  // a blocked clip shows its own thumbnail and opens on YouTube instead of a dead frame.
  if (!video.playable) {
    return (
      <div className={`${CARD} overflow-hidden ${REVEAL}`}>
        <a href={watchUrl} target="_blank" rel="noreferrer"
           className="group block relative aspect-video bg-raised">
          <img src={video.thumbnail} alt="" className="h-full w-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
          <span className="absolute inset-0 grid place-items-center">
            <span className="inline-flex items-center gap-2 px-4 min-h-11 rounded-lg bg-brand text-brand-fg text-sm font-semibold shadow-lg">
              Watch on YouTube <ExternalLink className="size-4" />
            </span>
          </span>
        </a>
        <div className="px-5 py-4">
          <p className="font-medium text-content leading-snug">{video.title}</p>
          <p className="text-sm text-subtle mt-1">
            {subtitle}{subtitle ? ' · ' : ''}<span className="text-subtle">the NFL does not allow this clip to play outside YouTube</span>
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className={`${CARD} overflow-hidden ${REVEAL}`}>
      <div className="aspect-video bg-ink">
        <iframe
          key={video.video_id}
          src={`https://www.youtube-nocookie.com/embed/${video.video_id}?autoplay=1&rel=0&modestbranding=1`}
          title={video.title}
          allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full border-0"
        />
      </div>
      <div className="px-5 py-4">
        <p className="font-medium text-content leading-snug">{video.title}</p>
        {subtitle && <p className="text-sm text-subtle mt-1">{subtitle}</p>}
      </div>
    </div>
  )
}

// A thumbnail that becomes the theater when clicked. maxres is missing on plenty of
// uploads, so this starts at hq and never has to fall back.
function Thumb({ video, className = '', playing }) {
  return (
    <span className={`relative shrink-0 overflow-hidden rounded-md bg-raised ${className}`}>
      <img src={video.thumbnail} alt="" loading="lazy"
           className="h-full w-full object-cover" />
      <span className={`absolute inset-0 grid place-items-center transition-opacity ${playing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
        <span className="grid place-items-center size-7 rounded-full bg-ink/70">
          <Play className="size-3.5 text-white translate-x-px" fill="currentColor" />
        </span>
      </span>
    </span>
  )
}

function PlayerRow({ p, activeId, onPick, dark }) {
  const accent = teamAccent(p.nfl_team, dark)
  const reel = p.videos.find(v => v.kind === 'reel')
  return (
    <li>
      <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
        <span className="w-1 h-7 rounded-full shrink-0" style={{ background: accent }} aria-hidden />
        <span className="font-medium text-content truncate">{p.name}</span>
        <span className={`font-mono text-xs font-semibold ${POS_COLORS[p.position] || 'text-subtle'}`}>{p.position}</span>
        {reel && (
          <Hint text="The NFL cut this player his own highlight reel for the week, which only happens after a standout game.">
            <span className="inline-flex items-center gap-1 text-xs text-mark"><Star className="size-3" fill="currentColor" />Reel</span>
          </Hint>
        )}
        <span className="ml-auto text-xs text-subtle whitespace-nowrap">
          {p.starting ? `started in ${p.starting}` : `benched in ${p.held}`}
        </span>
      </div>
      <ul className="flex flex-col">
        {p.videos.map(v => {
          const playing = v.video_id === activeId
          return (
            <li key={v.video_id}>
              <button
                onClick={() => onPick(v, p)}
                aria-current={playing || undefined}
                className={`group w-full text-left flex items-center gap-3 px-3 py-2 transition-colors ${playing ? 'bg-raised' : 'hover:bg-raised/60'}`}
              >
                <Thumb video={v} playing={playing} className="w-20 aspect-video" />
                <span className={`text-sm leading-snug line-clamp-2 ${playing ? 'text-content' : 'text-content'}`}>
                  {v.title}
                  {!v.playable && <ExternalLink className="inline size-3 ml-1 mb-0.5 text-subtle" aria-label="opens on YouTube" />}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </li>
  )
}

function VideoRow({ v, label, activeId, onPick }) {
  const playing = v.video_id === activeId
  return (
    <button
      onClick={() => onPick(v)}
      aria-current={playing || undefined}
      className={`group w-full text-left flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${playing ? 'bg-raised' : 'hover:bg-raised/60'}`}
    >
      <Thumb video={v} playing={playing} className="w-20 aspect-video" />
      <span className="min-w-0">
        <span className="block text-sm text-content leading-snug line-clamp-2">
          {v.title}
          {!v.playable && <ExternalLink className="inline size-3 ml-1 mb-0.5 text-subtle" aria-label="opens on YouTube" />}
        </span>
        {label && <span className="block text-xs text-subtle truncate mt-0.5">{label}</span>}
      </span>
    </button>
  )
}

function TapeSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_22rem] gap-5 items-start">
      <div className={CARD}>
        <Skeleton className="aspect-video rounded-none rounded-t-xl" />
        <div className="px-5 py-4 space-y-2">
          <Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/3" />
        </div>
      </div>
      <div className={`${CARD} p-3 flex flex-col gap-3`}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="w-20 aspect-video rounded-md shrink-0" />
            <div className="flex-1 space-y-1.5"><Skeleton className="h-3 w-full" /><Skeleton className="h-2.5 w-1/2" /></div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Tape() {
  const { credentials } = useApp()
  const dark = useTheme() === 'dark'
  const [data, setData] = useState(null)
  const [week, setWeek] = useState(null)
  const [error, setError] = useState(null)
  const [active, setActive] = useState(null)

  useEffect(() => {
    if (!credentials) return
    let cancelled = false
    getTape(week)
      .then(res => { if (!cancelled) { setData(res.data); setError(null) } })
      .catch(err => { if (!cancelled) setError(err.response?.data?.detail || 'Could not load this week of tape.') })
    return () => { cancelled = true }
  }, [credentials, week])

  // Open on the highest-stake player's best clip, so the page is never a dead frame.
  const opener = useMemo(() => {
    if (!data) return null
    // Lead with something that plays here: a blocked clip as the opener would make the
    // page look broken. The weekly compilation is the one the NFL lets us embed.
    const playable = data.compilations.find(c => c.playable)
    if (playable) return { video: playable, subtitle: `Week ${data.week}, every scorer included` }
    const p = data.players[0]
    if (p) return { video: p.videos[0], subtitle: `${p.name}, ${p.position}${p.nfl_team ? ` · ${p.nfl_team}` : ''}` }
    const c = data.compilations[0] || data.games[0]
    return c ? { video: c, subtitle: c.players?.join(', ') } : null
  }, [data])

  const stale = !!data && week != null && data.week !== week
  const current = active || opener

  if (!credentials) {
    return <div><h1 className="text-2xl font-display font-bold text-content mb-2">Tape</h1>
      <p className="text-subtle">Connect a league on the Dashboard to see your players' highlights.</p></div>
  }

  const weeks = data ? Array.from({ length: Math.max(1, data.current_week - 1) }, (_, i) => i + 1).reverse() : []

  return (
    <div className="flex flex-col gap-5">
      <div className={`flex flex-wrap items-baseline justify-between gap-3 ${REVEAL}`}>
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-display font-bold text-content">Tape</h1>
          {data && (
            <p className="text-sm text-subtle">
              {data.players.length
                ? `${data.players.length} of your ${data.roster_size} players on tape`
                : `no clips of your players in week ${data.week}`}
            </p>
          )}
        </div>
        {weeks.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-subtle">
            Week
            <select
              value={week ?? data?.week ?? ''}
              onChange={e => { setActive(null); setWeek(Number(e.target.value)) }}
              className="bg-surface border border-line rounded-md px-2 py-1 text-content"
            >
              {weeks.map(w => <option key={w} value={w}>{w}</option>)}
            </select>
          </label>
        )}
      </div>

      {error && <Notice tone="error" title={error} message="The highlights feed may be unavailable right now." actionLabel="Try again" onAction={() => setWeek(w => w)} />}
      {(!data || stale) && !error && <TapeSkeleton />}

      {data && !stale && !data.enabled && (
        <Notice tone="info" title="Highlights are switched off"
                message="Set YOUTUBE_API_KEY in .env and restart the backend to turn this page on." />
      )}

      {data && !stale && data.enabled && !current && (
        <Notice tone="info" title={`Nothing from week ${data.week} yet`}
                message="The NFL posts highlights within a day of each game. Check back after this week's games are played." />
      )}

      {data && !stale && current && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_22rem] gap-5 items-start">
          <Theater video={current.video} subtitle={current.subtitle} />

          <div className={`flex flex-col gap-4 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
            {data.players.length > 0 && (
              <section {...tiltHandlers} className={`${CARD} tilt overflow-hidden`}>
                <h2 className={`${H2} px-3 pt-3`}>Your players</h2>
                <p className="text-xs text-subtle px-3 pb-1">Ranked by how many of your lineups they started in</p>
                <ul className="divide-y divide-line/50">
                  {data.players.map(p => (
                    <PlayerRow key={p.player_id} p={p} dark={dark} activeId={current.video.video_id}
                      onPick={(v, pl) => setActive({ video: v, subtitle: `${pl.name}, ${pl.position}${pl.leagues.length ? ` · ${pl.leagues.join(', ')}` : ''}` })} />
                  ))}
                </ul>
              </section>
            )}

            {data.compilations.length > 0 && (
              <section {...tiltHandlers} className={`${CARD} tilt p-3`}>
                <h2 className={`${H2} mb-1`}>Plays here</h2>
                <p className="text-xs text-subtle mb-2">The weekly cut-ups, the only NFL videos that play outside YouTube</p>
                <div className="flex flex-col gap-1">
                  {data.compilations.map(v => (
                    <VideoRow key={v.video_id} v={v} activeId={current.video.video_id}
                      onPick={() => setActive({ video: v, subtitle: `Week ${data.week} compilation` })} />
                  ))}
                </div>
              </section>
            )}

            {data.games.length > 0 && (
              <section {...tiltHandlers} className={`${CARD} tilt p-3`}>
                <h2 className={`${H2} mb-1`}>Your games</h2>
                <p className="text-xs text-subtle mb-2">{data.games.length} games had a player of yours in them</p>
                <div className="flex flex-col gap-1">
                  {data.games.map(v => (
                    <VideoRow key={v.video_id} v={v} label={v.players.join(', ')} activeId={current.video.video_id}
                      onPick={() => setActive({ video: v, subtitle: v.players.join(', ') })} />
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
