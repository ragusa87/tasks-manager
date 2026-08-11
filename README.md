# Task Manager
A Django web task manager, based on the GTM™ Methodology (but not affiliated with it).

![Dashboard](docs/img/dashboard.png)

## Disclamer

This is a pet project, goal is to do some code-flow with IA.
I don't intent to maintain this project in the long term.

## Features
* Capture and manage tasks seamlessly
* Import existing tasks from NirvanaHQ (from the web UI or the command line — see [Nirvana import](#nirvana-import))
* Search and review tasks to decide on next actions
* Capture tasks by email: each user gets a secret inbox address, incoming mail becomes an inbox task (see [Email inbox](#email-inbox))
* Attach documents to tasks (PDF, images, audio), uploaded via drag & drop, stored on local disk or S3-compatible storage (see `STORAGE_URL`)
* Capture with the microphone or the camera: voice notes and photos become task attachments
* Offload: a mobile-first capture page, installable as an app (PWA)
* Batch actions: select tasks on the dashboard (or all matching a search) and apply an action to the whole selection
  * Tasks: add/remove a tag, add/replace/remove the area, move to another status (complete, cancel, next action, someday…) — every status transition that needs no extra input is offered, with a per-transition count of applicable items
  * Tags page: convert tags to areas or to contexts
  * Contexts page: convert contexts to tags or to areas
  * Areas page: convert areas to tags
  * Conversions move the items along (optionally merging into an existing destination and deleting the source); a confirmation modal previews how many items are affected, and items whose area would be overwritten are skipped, never overwritten

## Screenshots

* ![Item detail](docs/img/item_detail.png)
* ![Documents attached to a task](docs/img/item_documents.png)
* ![Recording a voice note on a task](docs/img/item_recording.png)
* ![Offload](docs/img/offload.png)
* ![Offload, recording a voice note](docs/img/offload_voice.png)
* ![Dashboard, light theme](docs/img/dashboard_light.png)

The screenshots (including the dashboard above) live in `docs/img/` and are
regenerated with `just capture-docs` against a running local instance.
**Warning: it resets the local database** (`just fixturize --clear`) to get
representative demo data before capturing.

## Nirvana import

Import a NirvanaHQ export (JSON) either from the web UI
(**Manage → Nirvana import**, runs in the background with live progress) or the
command line (`just manage nirvana_import <file.json> <username>`, add
`--delete` to wipe the user's existing data first).

### Known limitation: everything in `tags` becomes a Tag

NirvanaHQ classifies its labels into three kinds — **Areas**, **Contacts** and
**Contexts** (the three tabs of Nirvana's *Manage Tags…* dialog) — but its JSON
export flattens all three into a single comma-separated `tags` string on each
item, with **no field, prefix or ordering that marks which kind a label is**.
For example an item can carry `,personnal,liip-rawbot,ANALYSIS,Yannick Vaucher (C2C),`
mixing an area, a context and a contact indistinguishably (the tags are simply
stored alphabetically). Because the distinction is not recoverable from the
export, the importer maps **every** entry in `tags` to a GTD Tag — Areas are not
created and Contacts are not linked. This is a deliberate, accepted limitation:
the authoritative Area / Contact / Context split lives only in Nirvana's own UI,
so we don't attempt to reconstruct it. After importing you can reclassify from
the app — the Tags / Contexts / Areas management pages let you convert a tag
into an area or a context (see the batch-actions feature above).

Note: an item's *waiting-for* person is a separate `waitingfor` field and **is**
imported (into the task's "waiting for" person) — only tag-assigned contacts are
lost.

### TODOS
- New transition: Convert whole project to references
- DateTime picker could respect the user's locale.
- htmx show connectivity issue and 500.
- Allow checking item to archive them
- Delete archived item automatically after 30 days ?

## Linting and Formatting

```bash
ruff check .
ruff format .
```
You can also use pre-commit (`docker compose exec web pre-commit install`) or run `just pre-commit run --all-files`
## Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`

### Environment variables

All environment variables must be documented here (this is enforced as a project convention, see CLAUDE.md).

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret key, set a real one in production |
| `DEBUG` | — | Passed through docker-compose; settings modules set their own DEBUG |
| `ALLOWED_HOSTS` | `""` (dev: localhost + tasks.docker.test) | Space-separated list of allowed hosts |
| `DJANGO_SETTINGS_MODULE` | — | Settings module to use (see above) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | `task_processing` / `postgres` / `""` / `localhost` / `5432` | PostgreSQL connection; dev falls back to SQLite when `DB_NAME` is unset |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Celery result backend |
| `REDBEAT_REDIS_URL` | `CELERY_BROKER_URL` value | Redis URL for the RedBeat beat scheduler (stores the schedule in Redis) |
| `REDIS_CHANNEL_URL` | `redis://redis:6379/1` | Django Channels layer |
| `CACHE_URL` | `redis://127.0.0.1:6379/1` (prod), `redis://redis:6379/2` (dev) | Redis cache, shared between web and workers (e.g. import cancellation flags) |
| `STORAGE_URL` | `file://media` | Document storage: `file://<dir>` or `s3://key:secret@endpoint/bucket/prefix?region=...` |
| `DOCUMENT_PRESIGNED_URL_EXPIRY` | `300` | Expiry (seconds) of S3 presigned download URLs |
| `NIRVANA_IMPORT_HEARTBEAT_MAX_AGE` | `300` | Seconds without a heartbeat before a running Nirvana import is considered dead and cleaned up |
| `EMAIL_URL` | `console://` | Outgoing email backend DSN (dj-email-url format) |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | — / `587` / — / — | Outgoing SMTP (production settings only) |
| `EMAIL_INBOX_DSN` | `smtp://0.0.0.0:2525?max_size=10485760` | Incoming mail engine DSN, see [Email inbox](#email-inbox) |
| `USER_EMAIL_INBOX_DOMAIN` | `tasks.docker.test` | Domain part of per-user inbox addresses |
| `FRONTEND_URL` | `https://tasks.docker.test` | Public URL of the app |
| `CELERI_ADMIN_URL` | `http://tasks-celery-admin.docker.test/` | Flower dashboard URL |
| `IS_DEMO` | `True` | Show demo credentials on the login page |
| `CUSTOM_AUTHENTICATION_BACKEND` | `""` | Set to `authcrunch` (header roles) or `traefik-keycloak` (JWT-cookie roles) to authenticate via the reverse proxy |
| `LOGOUT_REDIRECT_URL` | `/login/` | Where to redirect after logout; behind the proxy, point at the Keycloak end-session endpoint |
| `AUTH_PROXY_COOKIE_NAME` | `AUTH_TOKEN` | Session cookie set by the auth proxy; deleted on logout |
| `AUTH_PROXY_OAUTH_CLIENT` | `tasks` | OAuth client whose `resource_access.<client>.roles` in the proxy JWT map to Django permissions (`traefik-keycloak`) |
| `AUTH_PROXY_SUPERUSER_ROLES` | `superuser` | Space-separated JWT client roles that grant `is_superuser` (`traefik-keycloak`) |
| `AUTH_PROXY_STAFF_ROLES` | `staff` | Space-separated JWT client roles that grant `is_staff` (`traefik-keycloak`) |
| `AUTH_PROXY_LOGOUT_FROM_JWT` | `False` | Derive the logout URL (Keycloak end-session endpoint) from the proxy JWT's issuer instead of `LOGOUT_REDIRECT_URL` |
| `SENTRY_DSN` | — | Enable Sentry error tracking (production settings only) |
| `DJANGO_VITE_DEV_SERVER_HOST` / `DJANGO_VITE_DEV_SERVER_PORT` / `DJANGO_VITE_DEV_SERVER_PROTOCOL` | `tasks-vite.docker.test` / `443` / `https` | Vite dev server (development settings only) |
| `NODE_ENV` / `VITE_ALLOWED_HOSTS` / `VITE_CORS_ORIGIN` | — | Frontend build environment (docker-compose) |
| `USER_ID` / `GROUP_ID` | `1000` | UID/GID used when building the dev images |

## Email inbox

Users can create tasks by sending an email to a personal, secret inbox address
(e.g. `inbox-x7k3f9q2@tasks.docker.test`). The subject becomes the task title,
the body its description, and allowed attachments (PDF, images, audio/voice
notes) are stored as documents on the task. The app only **receives** mail on
this channel, it never sends any.

### Enabling it for a user

Access is gated by the `use_email_inbox` permission, carried by the
**"Email inbox"** group (created by a migration). Add a user to that group in
the Django admin, then they get a "Email inbox" entry in the Manage menu where
they can:

* see and copy their inbox address, and regenerate it if it leaks,
* enable/disable the inbox,
* whitelist trusted sender addresses (mail from anyone else is rejected).

`just fixturize` sets up `user1` with the inbox `inbox-user1@$USER_EMAIL_INBOX_DOMAIN`
and whitelists `user1@example.com`.

### Running the listener

The `mail` docker-compose service runs `python manage.py mail_inbox`. The engine
is selected by the `EMAIL_INBOX_DSN` scheme:

```
smtp://0.0.0.0:2525?max_size=10485760      # local SMTP server (aiosmtpd), port 2525
imaps://user:pass@host:993/INBOX?poll=60   # poll a remote IMAP mailbox over TLS
imap://user:pass@host:143/INBOX?poll=60    # same, plaintext
```

`manage.py mail_inbox --host ... --port ...` overrides the DSN values.
Try the SMTP engine locally with `just mail-send inbox-user1@tasks.docker.test`.

**IMAP polling.** The engine connects to the mailbox every `poll` seconds
(default 60), runs each message through the same pipeline as SMTP, and enforces
the per-inbox policy via the message's recipient/sender:

* a message is turned into a task only if the addressed inbox is enabled
  ("Accept incoming email") **and** the `From` is a whitelisted trusted sender;
* **every message the engine handles is deleted** (flagged `\Deleted`, then
  expunged) so the mailbox never fills up — this includes mail dropped because
  the inbox is disabled or the sender is untrusted. Each outcome is logged
  (`Delivered mail …` / `Dropping mail … reason=…`) by the
  `task_processor.mail_inbox` logger. A transient/internal failure leaves the
  message in place to be retried on the next poll.

**Login username.** An `@` can't appear in the DSN userinfo (it would be read
as the host separator), so the login name is completed by appending the inbox
domain: `inbox-x` → `inbox-x@<USER_EMAIL_INBOX_DOMAIN>`. Override with the
`domain_in_username` query option — the leading `@` is **optional**, both forms
produce the same login name:

```
?domain_in_username=0                # send the username verbatim (no domain)
?domain_in_username=@example.com     # → inbox-x@example.com
?domain_in_username=example.com      # → inbox-x@example.com  (same thing)
```

**Dry run.** Add `?dry_run=1` to make the IMAP engine read-only: it connects,
resolves each message and logs the action it *would* take (`Would deliver …` /
`Dropping … would delete (dry-run)`), but creates no tasks and deletes no mail.
Point it at a live mailbox and watch the log before letting it consume the
inbox for real.

**Percent-encoding credentials.** The DSN is a URL, so reserved characters in
the username/password must be percent-encoded: `@` → `%40`, `:` → `%3A`, and —
importantly — a literal **`%` must be written as `%25`**. For example the
password `1129ku!GtL-%lV*F` is carried in the DSN as `1129ku!GtL-%25lV*F`; the
parser decodes `%25` back to a single `%`, so the server receives the exact
16-character password. (A stray `%` that isn't a valid `%XX` escape happens to
survive decoding, but relying on that is fragile — always encode it as `%25`.)
Keep the DSN in `.env` (git-ignored) — it holds the mailbox password.

### Security / operations notes

* **Anti-enumeration**: every permanent rejection (unknown address, disabled
  inbox, missing permission, non-whitelisted sender) returns the *same*
  `550 5.7.1 Recipient address rejected`, so probers cannot discover valid
  addresses or why they were blocked. The real reason is logged server-side.
* **Rate limiting**: per-sender, per-recipient and per-pair limits (see
  `EMAIL_INBOX_RATE_LIMITS` in settings) answer `450` (temporary failure); the
  per-sender check runs *before* recipient resolution so bulk probing is
  throttled first. Uses the Django cache; with a dummy cache it fails open.
* **Spoofing**: the MAIL FROM whitelist is hygiene, not authentication — FROM
  is trivially spoofable. The random inbox identifier is the actual secret;
  regenerate it if it leaks. SPF/DKIM checks are a possible future hardening.
* **Attachments**: max 5 per message, 10 MB each, content type sniffed from
  the bytes (python-magic), allowlist in `EMAIL_INBOX_ATTACHMENT_ALLOWED_TYPES`.
  Skipped attachments are noted in the task description.
* **Production**: the listener binds the unprivileged port 2525 and speaks
  plaintext. Put a real MTA or TCP proxy in front for port 25 and STARTTLS,
  e.g. postfix relaying the inbox domain to `[app-host]:2525`, and point the
  domain's MX record at it.
* **Logging**: the `task_processor.mail_inbox` logger records envelope
  addresses, verdicts and sizes — never subjects, bodies or attachments.
* **Shutdown**: SIGTERM/SIGINT trigger a graceful stop.


## Setup

Requirements:
- docker & docker-compose
- traefik (optional, only if you want to use it as reverse-proxy, expected network is pontsun)
- justfile (optional)

### Initialize the project

Just run:
```
cp .env.example .env
cp docker-compose.override.example.yaml docker-compose.override.yaml
docker compose up -d -f docker-compose.yaml -f docker-compose.dev.yaml
```

You need to wait for the container to be ready before accessing the web interface.
You can check the logs using: `docker compose logs -f web`

### Production setup

For production, you need to generate the config files first:

```bash
./bin/init.sh
```
The command above will create a docker-compose.override.yaml file for you (based on docker-compose.override.example.yaml) and create a .env file mostly ready for production.

WARNING: If you re-run the command again, all existing data in your database will be lost (we recreate the database volume).

#### Reverse proxy Authentication
You can configure django to use the reverse proxy for authentication. Two backends are available.

**Authcrunch (header roles)**
* Set `CUSTOM_AUTHENTICATION_BACKEND=authcrunch` in your docker-compose.override.yaml file and restart your containers.
* Configure your reverse proxy to set the `X-Token-User-Name` and `X-Token-User-Roles` so that django can identify the user.
* You need a role "authp/admin" to be super-admin.

**Traefik + Keycloak (JWT-cookie roles)**

For the [traefik keycloakopenid](https://github.com/lukaszraczylo/traefikoidc) plugin, roles are read from the Keycloak JWT stored in the `AUTH_TOKEN` cookie rather than a header.
* Set `CUSTOM_AUTHENTICATION_BACKEND=traefik-keycloak`.
* Configure the proxy to set `X-Token-User-Name` (used to identify the user) and to forward the JWT in the `AUTH_PROXY_COOKIE_NAME` cookie (`AUTH_TOKEN` by default).
* Assign roles to the user on the `AUTH_PROXY_OAUTH_CLIENT` OAuth client (`tasks` by default). Django maps them from `resource_access.<client>.roles`: the `superuser` role grants `is_superuser` and `staff` grants `is_staff` (configurable via `AUTH_PROXY_SUPERUSER_ROLES` / `AUTH_PROXY_STAFF_ROLES`). Roles are re-synced on every proxied page request.
* Set `AUTH_PROXY_LOGOUT_FROM_JWT=True` to derive the logout URL from the token's `iss` (Keycloak end-session endpoint), ending the upstream SSO session on logout.

> **Security — the proxy must control the cookie.** Django reads the JWT's claims **without verifying its signature**, so this backend is only safe when the reverse proxy is the sole authority over the `AUTH_PROXY_COOKIE_NAME` cookie. The proxy MUST:
> * validate the token against Keycloak (signature, expiry, audience) on every request it forwards, and reject/refresh invalid ones — the app trusts whatever the proxy lets through;
> * strip any client-supplied `X-Token-User-Name` header so a client cannot impersonate a user (both role sync and JWT-derived logout only run when this header is present, which the proxy sets only after validating the session).
>
> Because a cookie is client-controlled, a token that reaches Django unvalidated could carry forged roles — or, on logout, a forged issuer. Both cookie-reading paths are gated on the trusted header for this reason. Never expose the app directly (bypassing the proxy) with this backend enabled.

> **Session expiry / token refresh.** The `AUTH_TOKEN` access token is short-lived (Keycloak defaults to 5–15 min). Django keeps its own session alive across that expiry, but the proxy re-challenges Keycloak once the access token lapses. Django cannot refresh the token — it holds neither the refresh token nor the client secret. To avoid frequent re-authentication, enable token refresh in the proxy plugin and/or raise the Keycloak client's *SSO Session Idle* / *Max* lifetimes.

## License

Copyright (C) 2026 Laurent Constantin

This program is free software: you can redistribute it and/or modify it under
the terms of the **GNU Affero General Public License** as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. See the [LICENSE](LICENSE) file for the full text.

In short, the AGPL lets anyone use, modify and self-host this software —
including for commercial purposes — **on the condition that any modified version
(including one offered to users over a network) is also released under the AGPL,
with its source code made available.**

### Commercial license

If you want to use this software in a way that is incompatible with the AGPL —
for example, embedding it in a closed-source product or offering it as a hosted
service without publishing your modifications — a separate **commercial license
is available on request.**

See [CONTRIBUTING.md](CONTRIBUTING.md) for how contributions are handled (a CLA
is required so this dual-licensing stays possible).
