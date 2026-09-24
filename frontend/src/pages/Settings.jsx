import { useState, useEffect, useRef } from 'react'
import { getLeagues, getEspnStatus, saveEspn, removeEspn, lookupEspnLeague, addPublicEspnLeague, removeEspnLeague } from '../services/api'
import { toast } from 'sonner'
import { useApp } from '../context/AppContext'
import WeightSlider from '../components/WeightSlider'
import Spinner from '../components/Spinner'
import { parseEspnCookies } from '@/lib/utils'

// Neither espn_s2 nor SWID is HttpOnly (checked against live Set-Cookie headers,
// 2026-09-24), so one click on espn.com can read both. This is the whole reason we don't
// need the browser extension FantasyPros ships for the same job.
const BOOKMARKLET = "javascript:(function(){"
  + "var c=document.cookie,g=function(n){var m=c.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));return m?m[1]:''};"
  + "var a=g('espn_s2'),b=g('SWID');"
  + "if(!a||!b){alert('Log in to espn.com first, then click this again.');return}"
  + "var t='espn_s2='+a+'; SWID='+b;"
  + "if(navigator.clipboard){navigator.clipboard.writeText(t).then("
  + "function(){alert('Copied. Paste it into Fantas.ai settings.')},function(){prompt('Copy this:',t)})}"
  + "else{prompt('Copy this:',t)}"
  + "})()"

const field = 'bg-raised border border-line rounded-lg px-3 py-2 text-sm text-content placeholder-subtle/60 focus:outline-none focus:border-brand'
const btnPrimary = 'bg-brand hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed text-brand-fg text-sm font-semibold rounded-lg transition-all'

function Section({ title, description, children }) {
  return (
    <div className="bg-surface border border-line rounded-xl p-6">
      <h2 className="text-base font-display font-semibold text-content mb-1">{title}</h2>
      {description && <p className="text-sm text-subtle mb-5">{description}</p>}
      {children}
    </div>
  )
}

// ── Projection Weights ────────────────────────────────────────────────────────
function WeightsSection() {
  const { weights, weightsLoaded, saving, saveError, updateWeight, saveWeights } = useApp()
  const [saved, setSaved] = useState(false)
  const sum   = Math.round((weights.weight_sleeper + weights.weight_espn + weights.weight_fp) * 100)
  const sumOk = sum === 100

  const handleChange = (key, value) => { setSaved(false); updateWeight(key, value) }
  const handleSave = async () => {
    await saveWeights(weights)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Section
      title="Projection Weights"
      description="How Sleeper, ESPN, and FantasyPros projections are blended into the weighted score. Must total 100%."
    >
      {!weightsLoaded ? <Spinner label="Loading weights" /> : (
        <div className="flex flex-col gap-5 max-w-sm">
          <WeightSlider label="Sleeper"     value={weights.weight_sleeper} onChange={v => handleChange('weight_sleeper', v)} />
          <WeightSlider label="ESPN"        value={weights.weight_espn}    onChange={v => handleChange('weight_espn', v)} />
          <WeightSlider label="FantasyPros" value={weights.weight_fp}      onChange={v => handleChange('weight_fp', v)} />
        </div>
      )}
      <div className="flex items-center gap-4 mt-6">
        <button onClick={handleSave} disabled={!sumOk || saving} className={`px-4 py-2 ${btnPrimary}`}>
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Weights'}
        </button>
        <span className={`text-sm font-mono tabular-nums ${sumOk ? 'text-subtle' : 'text-bear'}`}>Total: {sum}%</span>
      </div>
      {saveError && <p className="text-bear text-sm mt-2">{saveError}</p>}
    </Section>
  )
}

// ── League Setup ──────────────────────────────────────────────────────────────
function LeagueSection() {
  const { credentials, saveCredentials } = useApp()
  const [username, setUsername]   = useState(credentials?.username || '')
  const [leagues, setLeagues]     = useState([])
  // "PLATFORM:league_id", since the list mixes Sleeper and ESPN leagues
  const [leagueKey, setLeagueKey] = useState(credentials ? `${credentials.platform}:${credentials.leagueId}` : '')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [saved, setSaved]         = useState(false)

  useEffect(() => {
    if (username) loadLeagues(username)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadLeagues = async (u) => {
    if (!u.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await getLeagues(u.trim())
      const list = res.data.leagues || []
      setLeagues(list)
      if (!list.find(l => `${l.platform}:${l.league_id}` === leagueKey) && list.length) setLeagueKey(`${list[0].platform}:${list[0].league_id}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Sleeper user not found.')
      setLeagues([])
    } finally {
      setLoading(false)
    }
  }

  const handleSave = () => {
    if (!username || !leagueKey) return
    const [platform, leagueId] = leagueKey.split(':')
    saveCredentials(username.trim(), leagueId, platform)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Section title="League Setup" description="Your Sleeper username and the league to track on the Dashboard.">
      <div className="flex flex-col gap-3 max-w-sm">
        <div>
          <label className="block text-sm text-subtle mb-1">Sleeper Username</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={username}
              onChange={e => { setUsername(e.target.value); setLeagues([]); setSaved(false) }}
              onKeyDown={e => e.key === 'Enter' && loadLeagues(username)}
              placeholder="your username"
              className={`flex-1 ${field}`}
            />
            <button
              onClick={() => loadLeagues(username)}
              disabled={loading || !username.trim()}
              className="px-3 py-2 bg-raised hover:bg-line disabled:opacity-40 text-content text-sm rounded-lg border border-line transition-colors"
            >
              {loading ? '...' : 'Find'}
            </button>
          </div>
        </div>

        {error && <p className="text-bear text-sm">{error}</p>}

        {leagues.length > 0 && (
          <div>
            <label className="block text-sm text-subtle mb-1">Active League</label>
            <select value={leagueKey} onChange={e => { setLeagueKey(e.target.value); setSaved(false) }} className={`w-full ${field}`}>
              {leagues.map(l => <option key={`${l.platform}:${l.league_id}`} value={`${l.platform}:${l.league_id}`}>{l.name}{l.platform === 'ESPN' ? ' (ESPN)' : ''}</option>)}
            </select>
          </div>
        )}

        <button onClick={handleSave} disabled={!username || !leagueKey} className={`w-fit px-4 py-2 ${btnPrimary}`}>
          {saved ? 'Saved!' : 'Save League'}
        </button>
      </div>
    </Section>
  )
}

// Public ESPN leagues need no cookies: paste the link, pick your team.
function PublicLeagueForm() {
  const { leagues, reloadLeagues } = useApp()
  const [link, setLink]     = useState('')
  const [found, setFound]   = useState(null)   // { league_id, name, teams }
  const [teamId, setTeamId] = useState('')
  const [busy, setBusy]     = useState(false)
  const [error, setError]   = useState(null)
  const added = leagues.filter(l => l.platform === 'ESPN' && l.public)

  const find = async () => {
    setBusy(true); setError(null); setFound(null)
    try {
      const res = await lookupEspnLeague(link.trim())
      setFound(res.data); setTeamId(String(res.data.teams[0]?.team_id ?? ''))
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn't reach ESPN. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const add = async () => {
    setBusy(true); setError(null)
    try {
      await addPublicEspnLeague(found.league_id, Number(teamId))
      toast.success(`Added ${found.name}. Pick it in the league switcher.`)
      setFound(null); setLink('')
      reloadLeagues()
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn't add that league.")
    } finally {
      setBusy(false)
    }
  }

  const remove = async (l) => {
    await removeEspnLeague(l.league_id).catch(() => {})
    toast(`Removed ${l.name}.`)
    reloadLeagues()
  }

  return (
    <div className="flex flex-col gap-3 max-w-sm">
      <h3 className="text-sm font-medium text-content">Add a public league</h3>
      <p className="text-sm text-subtle">If your league manager made the league public, paste its link. No ESPN login needed.</p>
      <div className="flex gap-2">
        <input
          value={link}
          onChange={e => { setLink(e.target.value); setFound(null) }}
          onKeyDown={e => e.key === 'Enter' && link.trim() && find()}
          placeholder="fantasy.espn.com/football/league?leagueId=..."
          className={`flex-1 min-w-0 ${field}`}
        />
        <button onClick={find} disabled={busy || !link.trim()} className="px-3 py-2 bg-raised hover:bg-line disabled:opacity-40 text-content text-sm rounded-lg border border-line">
          Find
        </button>
      </div>
      {found && (
        <>
          <label htmlFor="espn-team" className="text-sm text-content">Which team is yours in {found.name}?</label>
          <select id="espn-team" value={teamId} onChange={e => setTeamId(e.target.value)} className={field}>
            {found.teams.map(t => <option key={t.team_id} value={t.team_id}>{t.name}{t.owner ? ` (${t.owner})` : ''}</option>)}
          </select>
          <button onClick={add} disabled={busy || !teamId} className={`w-fit px-4 py-2 ${btnPrimary}`}>Add league</button>
        </>
      )}
      {error && <p className="text-bear text-sm">{error}</p>}
      {added.length > 0 && (
        <ul className="text-sm divide-y divide-line border border-line rounded-lg">
          {added.map(l => (
            <li key={l.league_id} className="flex items-center justify-between px-3 py-2">
              <span className="text-content truncate">{l.name}</span>
              <button onClick={() => remove(l)} className="text-xs text-subtle hover:text-bear">Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── ESPN account ──────────────────────────────────────────────────────────────
// Cookies are write-only: the API checks them against ESPN, saves them, and never sends
// them back, so this form only ever shows connected / not connected.
function ESPNSection() {
  const { reloadLeagues, refreshEspnStatus } = useApp()
  const [connected, setConnected] = useState(null)
  const [expired, setExpired]     = useState(false)
  const [s2, setS2]               = useState('')
  const [swid, setSwid]           = useState('')
  const [busy, setBusy]           = useState(false)
  const [error, setError]         = useState(null)
  const [found, setFound]         = useState(null)
  // React refuses to render a javascript: href, so the bookmarklet goes on via the DOM.
  const bookmarkRef = useRef(null)
  useEffect(() => { if (bookmarkRef.current) bookmarkRef.current.href = BOOKMARKLET }, [connected, expired])

  // One paste fills both fields: the bookmarklet hands over a cookie string, not a value.
  const onS2Change = (v) => {
    const parsed = parseEspnCookies(v)
    if (parsed) { setS2(parsed.espn_s2); setSwid(parsed.swid) } else { setS2(v) }
  }

  // Expired cookies show the connect form again, with a note, instead of "Connected".
  useEffect(() => {
    getEspnStatus()
      .then(res => { setExpired(res.data.needs_reconnect); setConnected(res.data.connected && !res.data.needs_reconnect) })
      .catch(() => setConnected(false))
  }, [])

  const connect = async () => {
    setBusy(true); setError(null)
    try {
      const res = await saveEspn(s2.trim(), swid.trim())
      setConnected(true); setExpired(false); setFound(res.data.leagues); setS2(''); setSwid('')
      reloadLeagues(); refreshEspnStatus()
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn't reach ESPN. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    await removeEspn().catch(() => {})
    setConnected(false); setFound(null)
    reloadLeagues(); refreshEspnStatus()
  }

  return (
    <Section
      title="ESPN leagues"
      description="Add ESPN leagues next to your Sleeper ones in the league switcher."
    >
      <PublicLeagueForm />
      <div className="border-t border-line my-6" />
      <h3 className="text-sm font-medium text-content mb-1">Private leagues: connect your ESPN account</h3>
      <p className="text-sm text-subtle mb-3">Finds every ESPN league you're in, public or private.</p>
      {connected === null ? <Spinner label="Checking your ESPN connection" /> : connected ? (
        <div className="flex flex-col gap-3 max-w-sm">
          <p className="text-sm text-content">
            Connected.{' '}
            {found && (found.length
              ? `Found ${found.length === 1 ? '1 league' : `${found.length} leagues`}: ${found.map(l => l.name).join(', ')}.`
              : 'No ESPN football leagues found for this season.')}
          </p>
          <button onClick={disconnect} className="w-fit px-3 py-1.5 text-sm text-subtle border border-line rounded-lg hover:text-content hover:bg-raised">
            Disconnect ESPN
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3 max-w-sm">
          {expired && <p className="text-sm text-warn">ESPN stopped accepting your saved cookies. Paste fresh ones to reconnect.</p>}
          <p className="text-sm text-subtle">
            Drag <a ref={bookmarkRef} href="#" onClick={e => e.preventDefault()}
              className="font-medium text-content underline decoration-mark decoration-2 underline-offset-2 cursor-grab">Get ESPN cookies</a>{' '}
            to your bookmarks bar. Then open espn.com and click it, and paste below.
          </p>
          <p className="text-xs text-faint">
            Or copy <span className="font-mono">espn_s2</span> and <span className="font-mono">SWID</span> by hand from developer tools, Application, then Cookies.
          </p>
          <input type="password" autoComplete="off" value={s2} onChange={e => onS2Change(e.target.value)} placeholder="espn_s2, or paste both here" className={field} />
          <input type="password" autoComplete="off" value={swid} onChange={e => setSwid(e.target.value)} placeholder="SWID" className={field} />
          {error && <p className="text-bear text-sm">{error}</p>}
          <button onClick={connect} disabled={busy || !s2.trim() || !swid.trim()} className={`w-fit px-4 py-2 ${btnPrimary}`}>
            {busy ? 'Checking with ESPN' : 'Connect ESPN'}
          </button>
        </div>
      )}
    </Section>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function Settings() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-display font-bold text-content mb-6">Settings</h1>
      <div className="flex flex-col gap-5">
        <WeightsSection />
        <LeagueSection />
        <ESPNSection />
      </div>
    </div>
  )
}
