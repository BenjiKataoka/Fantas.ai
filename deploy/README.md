# Deploying Fantas.ai (free tier)

Backend on an Oracle Cloud Always Free ARM server, frontend on Vercel Hobby, sign-in on
Clerk development keys, database already on Neon. Total cost: $0.

The server holds **no data**: everything lives in Neon. If Oracle reclaims it (it can
reclaim idle Always Free servers), you lose uptime, not data. Rebuild by rerunning
steps 2 to 5. The one file you cannot recreate is `/opt/fantasai/.env`, so keep a copy.

## 1. Accounts (you, ~20 min)

1. **Oracle Cloud**: sign up and pick **US East (Ashburn)** or **US Midwest (Chicago)** as the
   home region. It is permanent, Always Free resources only exist there, and the database
   is in AWS us-east-2 (Ohio): every request makes several database round trips, so
   distance adds up.
2. **Create an instance**: shape `VM.Standard.A1.Flex` (Ampere, e.g. 2 OCPU / 12 GB),
   image **Ubuntu 24.04**, add your SSH public key. "Out of capacity" is common: retry, try
   another availability domain, or a smaller size.
3. **Reserve the public IP** (Networking > Reserved public IPs) so it survives a restart.
4. **Open ports 80 and 443** in the instance's VCN security list: two ingress rules, TCP,
   source `0.0.0.0/0`. (`setup.sh` opens the server's own firewall; this is the cloud half.)
5. **DuckDNS** (duckdns.org, free): create a subdomain and point it at the reserved IP.

## 2. Server setup (once)

```bash
scp -r deploy ubuntu@<server-ip>:~/
ssh ubuntu@<server-ip>
sudo bash deploy/setup.sh yourapp.duckdns.org
sudo nano /opt/fantasai/.env        # fill in every REQUIRED line
```

`ESPN_COOKIE_KEY` must be **the same value as your laptop's `.env`**.

## 3. Ship the backend (every deploy)

From your laptop, with everything committed:

```bash
deploy/push.sh ubuntu@<server-ip>
deploy/smoke.sh https://yourapp.duckdns.org
```

`push.sh` installs the exact lock, runs migrations **before** switching releases (a failed
migration leaves the old release serving) and keeps the previous release for rollback.

## 4. Frontend on Vercel

1. In `frontend/vercel.json`, replace `REPLACE-WITH-BACKEND-HOST` with `yourapp.duckdns.org`
   and commit.
2. `git push`: Vercel builds from GitHub, and local commits are not there until you
   push them. Then import the repo into Vercel with **Root Directory `frontend`**.
3. Add the environment variable `VITE_CLERK_PUBLISHABLE_KEY` (your `pk_test_...` key).
4. Deploy, then put the exact Vercel URL into `ALLOWED_ORIGINS` in the server's `.env`
   and restart: `sudo systemctl restart fantasai`. Sign-in fails until they match.

## 5. After it is live

- Set `SCHEDULER_ENABLED=false` in your **laptop's** `.env`. Two schedulers would sync
  every league twice and spend the free Gemini quota twice.
- Sign in on the deployed site, then approve your friends in Admin as they sign up.
- The content policy ships **report-only**. Open each page, check the browser console
  for violations, and only then consider enforcing it (see plan.md).

## Useful commands on the server

```bash
sudo systemctl status fantasai            # is it running
sudo journalctl -u fantasai -n 100 -f     # backend logs
sudo journalctl -u caddy -n 50            # HTTPS / certificate problems
cat /opt/fantasai/backend/REVISION        # which commit is live
```
