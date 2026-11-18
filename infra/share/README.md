# Share this PC's Mentor server

A trial setup without a rented server: the gateway runs on one Windows PC and everyone who installed the app reaches it
at a fixed address, **https://app.mentor-hoc.workers.dev/api**. That address is compiled into the GitHub Release
installers (`.github/workflows/desktop-installers.yml`).

How it works: a Cloudflare quick tunnel (free, no domain) exposes `localhost:8000`, but its `*.trycloudflare.com`
address changes at every start. `share-up.ps1` writes the new address into a Workers KV key, and the worker in
`worker.js` (on `mentor-hoc.workers.dev`) passes every request through to it.

## Every day

```powershell
powershell -ExecutionPolicy Bypass -File infra\share\share-up.ps1
```

It starts the router and the gateway if they are not running, opens the tunnel, points the worker at it, and keeps the
PC awake. Keep the window open; close it to stop sharing. While the PC is off, the app shows the server as offline.

## First-time setup (done once, already done for mentor-hoc)

1. `winget install Cloudflare.cloudflared`
2. `powershell -ExecutionPolicy Bypass -File infra\share\cf-token.ps1`: create the API token (Workers Scripts edit,
   Workers KV edit, Account Settings read) and save it as `CLOUDFLARE_WORKERS_TOKEN` in `.env.dev.local`.
3. The account needs a workers.dev subdomain (`PUT /accounts/{id}/workers/subdomain`) and a KV namespace named
   `mentor-share`; its id goes in `wrangler.toml`.
4. Deploy the worker with the token in `CLOUDFLARE_API_TOKEN`: `npx wrangler@4.20.0 deploy`, then enable its workers.dev
   route (`POST /accounts/{id}/workers/scripts/app/subdomain` with `{"enabled":true}`).

A different account gets a different subdomain: change `$Public` in `share-up.ps1` and the default address in the
workflow (or set the repository variable `MENTOR_API_BASE`), then release new installers.

When a real server exists (infra/deploy.sh), set `MENTOR_API_BASE` to `https://<domain>/api` and release again.
