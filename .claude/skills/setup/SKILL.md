---
name: setup
description: Set up a new Money Doctor deployment step by step - .env, compose file, optional email relay, Cloudflare Tunnel, single sign-on, first login, iPhone Shortcuts, bank sync and the calendar feed. Use when someone is installing Money Doctor, moving it to a server, or something in their deployment isn't working.
---

# Set up Money Doctor

Walk the person through it one stage at a time and check each stage works
before moving on. They may not be technical: say what each step is for in one
sentence, and do the typing for them where you can.

**Secrets:** never ask for a password, app password, tunnel token or
SimpleFIN token in chat. Say which file and key to paste it into, and let
them do it. Secrets you generate yourself (`MD_SECRET`, the oauth2-proxy
cookie secret) you can write straight into the file without printing them.

## 1. Ask how they'll use it

Ask these together, with a recommendation:

1. **Reaching it from the phone.** Shortcuts, Apple Pay logging and the
   calendar need a public HTTPS address.
   - Cloudflare Tunnel (recommended): free, no open ports, needs a domain on Cloudflare. Profile `tunnel`.
   - Their own reverse proxy (Caddy, Traefik, nginx): README "Deploying it". Profile `nginx` is optional.
   - Home network or VPN only: no profile; Shortcuts only work at home or on the VPN.
2. **Morning email.**
   - Gmail straight from the app (simplest): an app password in `.env`.
   - Postfix relay (profile `email`): queues and retries; same Gmail app password, in `deploy/postfix.env`.
   - None for now.
3. **Login.** A password (default) or their existing single sign-on
   (Keycloak, Authelia, Authentik, Google) through oauth2-proxy (profile `sso`).

## 2. Files

Check `docker compose version` works first. From the repo root:

```bash
cp .env.example .env
cp compose.example.yml compose.yml
mkdir -p data && cp config/budget.example.yaml data/budget.yaml
sudo chown -R 1000:1000 data          # the container runs as uid 1000
```

In `.env`:
- `MD_SECRET`: generate with `openssl rand -hex 32` and write it in.
- `MD_PASSWORD`: they set it themselves.
- `MD_PUBLIC_URL`: the address they'll open (e.g. `https://money.example.com`),
  or `http://localhost:8000` for now.
- `TZ`: their time zone (the container clock), e.g. `America/Chicago`.
- `COMPOSE_PROFILES`: the profiles from step 1, comma-separated.

For each profile, copy the example and point them at the keys to fill:

| Profile | File | They fill in |
|---|---|---|
| `email` | `deploy/postfix.env` | `RELAYHOST_USERNAME`, `RELAYHOST_PASSWORD` (Gmail app password: myaccount.google.com/apppasswords, needs 2-Step Verification). Then `.env`: `SMTP_HOST=postfix`, `SMTP_PORT=25`, `SMTP_FROM=Money Doctor <their gmail>` |
| `tunnel` | `deploy/cloudflared.env` | `TUNNEL_TOKEN`. Cloudflare: Zero Trust -> Networks -> Tunnels -> Create (Cloudflared), add a Public Hostname with service `HTTP` `nginx:8080` |
| `sso` | `deploy/oauth2-proxy.env` | Issuer URL, client id and secret from their provider; generate the cookie secret. Then `.env`: `MD_NGINX_CONF=money-doctor-sso.conf`, `MD_AUTH=proxy`, `MD_TRUSTED_PROXIES=172.30.50.10` |

Direct Gmail without postfix: `.env` `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, `SMTP_STARTTLS=true`, `SMTP_USER`, `SMTP_PASSWORD`.

Once a tunnel or proxy is in front, they can remove the `127.0.0.1:8000`
port from `compose.yml`, or keep it for local access.

## 3. Start and check

```bash
docker compose up -d --build
docker compose ps                     # everything "healthy" after ~30 s
curl -s localhost:8000/healthz        # {"ok": true}
docker compose logs --tail 50 money-doctor
```

Then open `MD_PUBLIC_URL` and log in.

| Symptom | Likely cause |
|---|---|
| `PermissionError` on `/data` | `data/` isn't owned by uid 1000: `sudo chown -R 1000:1000 data` |
| `Pool overlaps with other one on this host` | Change the subnet in `compose.yml`, and the fixed addresses and `MD_TRUSTED_PROXIES` with it |
| Tunnel host gives 502 / 1033 | The Cloudflare public hostname must point at `http://nginx:8080`; check `docker compose logs cloudflared` |
| Login doesn't stick | `MD_PUBLIC_URL` must match the address they open (https vs http) |
| Email "not sent: set SMTP_HOST and digest.to" | Set both: `SMTP_HOST` in `.env`, `digest.to` in `data/budget.yaml` |
| Email accepted but never arrives | `docker compose logs postfix`: `535` = wrong app password, `status=sent` = delivered (check spam) |
| SSO loops or 403 | The redirect URL in the provider must be exactly `{MD_PUBLIC_URL}/oauth2/callback` |

## 4. In the app

Point them at **Settings -> iPhone setup** (`/setup`), which has their own
URLs filled in. In order:

1. **Budget**: use the `budget` skill to replace the example budget.
2. **API token**: Settings -> Shortcut tokens. Shown once; it goes in the
   Shortcuts, not in chat.
3. **Shortcuts**: recipes in `docs/shortcuts.md`.
4. **Bank sync** (optional, about $15/yr): a SimpleFIN Bridge account, link
   the bank, paste the setup token in Settings -> SimpleFIN Bridge, map each account.
5. **Calendar**: Settings -> Calendar subscription gives a subscribe link for Apple or
   Google Calendar. The link is the password; reset it there if it leaks.
6. **Email test**: Settings -> Send now.
7. **Payment emails** (optional, Settings -> Email receipts): a Gmail label plus `MAIL_USER` /
   `MAIL_PASSWORD` in `.env`, then `docker compose up -d`.

## Updating and backups

```bash
git pull && docker compose up -d --build
sqlite3 data/money.db ".backup data/money-backup.db"    # or copy data/ while stopped
```

`data/` is everything; back it up somewhere off the machine.
