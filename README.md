# Fantas.ai

A fantasy football assistant for my redraft league. It pulls every team you own across
Sleeper and ESPN into one place, blends three projection sources into one number per
player, and tells you who to start, who to pick up, and how last week went.

![The portfolio view: every league at once, with a projected record for the week](docs/screenshots/dashboard.png)

**What it does**

- **Portfolio**: all your leagues on one board, with live scores during games and a projected record for the week.
- **Start/Sit**: the best legal lineup for your league's real slots (FLEX, Superflex, DEF), plus the close calls.
- **Waivers**: the free agents who would actually beat one of your starters over the next four weeks.
- **Recap**: a finished week graded: points you left on the bench, and which projection source was closest.
- **Player tracker**: an AI read on each player's outlook from career stats, news and ADP, tracked over the season.

**Status**: live and invite-only for my league while it's in development. A public demo
account is coming.

## Screenshots

| Start/Sit | Waivers |
|---|---|
| ![Recommended lineup with close calls](docs/screenshots/startsit.png) | ![Free agents ranked against your starters](docs/screenshots/waivers.png) |
| **Recap** | **Player tracker** |
| ![A finished week, projected against actual](docs/screenshots/recap.png) | ![One player's outlook and trend](docs/screenshots/tracker.png) |

<p align="center">
  <img src="docs/screenshots/phone.png" alt="The portfolio on a phone" width="260">
</p>

## How it's built

```mermaid
flowchart LR
    user([Browser]) --> vercel[Vercel<br/>React + Vite]
    vercel -- "/api rewrite" --> caddy[Caddy, HTTPS<br/>Oracle Cloud ARM VM]
    caddy --> api[FastAPI<br/>+ scheduler]
    api --> neon[(Neon Postgres)]
    api --> clerk[Clerk<br/>sign-in]
    api --> sleeper[Sleeper API]
    api --> espn[ESPN Fantasy API]
    api --> fp[FantasyPros]
    api --> news[RotoWire, ESPN, RSS news]
    api --> gemini[Gemini<br/>Flash-Lite]
```

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, shadcn/ui |
| Backend | Python, FastAPI (async), SQLAlchemy 2 async + asyncpg, Alembic |
| Database | Neon serverless Postgres |
| Auth | Clerk, with JWTs verified on the server and an admin approval gate |
| AI | Google Gemini (Flash-Lite), on the free tier |
| Jobs | APScheduler in the API process: roster sync, market data, player analysis |
| Hosting | Oracle Cloud Always Free (API), Vercel (frontend), DuckDNS + Caddy for HTTPS |

Total hosting cost is $0. The server holds no data, so if it disappears the rebuild is one
script ([deploy/](deploy/README.md)).

## Engineering decisions

A few problems that turned out to be more interesting than they looked.

**Three sources disagree on who a player is.** Sleeper, ESPN and FantasyPros each have
their own ids, and names don't line up either ("Texans D/ST" vs "Houston Texans"). Sleeper
ids are the canonical key; ESPN players are mapped by stored id first, then by normalized
name and position. Team defenses had no ESPN id at all, so a league with a DEF slot came up
one starter and about 8 points short. ESPN encodes defenses as `-(16000 + proTeamId)`,
which I verified against all 32 teams before relying on it.

**An access-control audit of all 18 routes that take an id.** Thirteen were scoped
correctly. The finding was a `sleeper_username` query parameter the server trusted: one
request with someone else's username silently rebound your account to their Sleeper
identity and synced a stranger's roster into your dashboard, while the error path claimed
an ownership check it never made. The username is now pinned to the account your login
connected (anything else gets a 403), and a disconnect endpoint exists so a typo on first
connect isn't permanent.

**Measuring for rate limits found a bigger bug.** Every API request was calling Clerk's
servers (46 calls for 39 requests) and throwing the answer away. With a dozen users that
would have run into Clerk's own rate limits on sign-in. Now only a brand-new user triggers
the lookup, and a typical request went from 365 ms to 251 ms. The rate limits themselves
are keyed on the verified user, so a forged token can't spend someone else's allowance.

**Third-party credentials are encrypted, and failure is recoverable.** ESPN private
leagues need the user's session cookies. They're stored with Fernet encryption, are
write-only through the API, and a cookie that fails to decrypt (say, after a key rotation)
reads as missing, so the user is asked to reconnect instead of being locked out.

**Fitting a 4-pass AI pipeline into a free tier.** Gemini's free tier meters each model
separately: roughly 500 requests a day on Flash-Lite, but only about 20 on Flash. One
player's analysis takes four calls, so a single roster on Flash would exhaust a day's
budget. Every pass runs on Flash-Lite behind a per-model daily cap, and because a player's
outlook doesn't depend on who asks, each analysis is cached globally and shared by every
user who rosters him.

**The API said the videos would play. They didn't.** The highlights page embeds NFL
clips from YouTube. Both the Data API and oEmbed report all 200 recent NFL uploads as
embeddable, but in testing, 24 of 24 game highlights and player reels were blocked on
every third-party site, because the rights holder's block isn't what those flags describe.
The app now checks the actual embed page for each video before showing it.

**Intermittent sign-in failures came down to rounding.** A small share of fresh logins
failed with "token is not yet valid". Clerk stamps a token's issue time in whole
seconds, so it can land a fraction of a second ahead of the server's clock. A 5-second
leeway, matching Clerk's own SDK, fixed it, with a test that signs real tokens a few
seconds in the future.

## Running it locally

You need Python 3.14, Node 20.19+ or 22.12+, a Postgres database (Neon's free tier works), a Gemini API
key and a Clerk application.

```bash
cp .env.example .env                  # fill in the values; each one is documented there

python3 -m venv backend/venv && source backend/venv/bin/activate
pip install -r backend/requirements.lock
cd backend && alembic upgrade head && uvicorn main:app --reload --port 8000

cd frontend && npm install && npm run dev     # http://localhost:3000
```

Without `CLERK_SECRET_KEY`, the API runs as a single local user with sign-in turned off.

**Tests**: 28 backend test files, one per service or router, each runnable on its own
(`python3 tests/test_waiver_service.py` from `backend/`). Pure logic like lineup solving
and win probability is tested against hand-checked numbers; the router tests hit a real
database.

## About

Built by Benjamin Kataoka. [LinkedIn](https://www.linkedin.com/in/benjamin-kataoka/)

Player and league data belong to Sleeper, ESPN and FantasyPros. This is a personal project
with no affiliation to any of them or to the NFL.
