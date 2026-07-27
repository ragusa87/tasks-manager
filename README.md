# Task Manager
A Django web task manager, based on the GTM™ Methodology (but not affiliated with it).

<img width="1271" height="872" alt="image" src="https://github.com/user-attachments/assets/b5b5e46a-fbd9-421a-8f94-b550b69cdce7" />

## Disclamer

This is a pet project, goal is to do some code-flow with IA.
I don't intent to maintain this project in the long term.

## Features
* Capture and manage tasks seamlessly
* Import existing tasks from NirvanaHQ (via command line)
* Search and review tasks to decide on next actions
* Capture tasks by email: each user gets a secret inbox address, incoming mail becomes an inbox task (see [Email inbox](#email-inbox))

### TODOS
- Nirvana: UI for import, fix importing reference (parent reference is currently a project instead of a reference)
- Bach actions support: `tag<->area` conversion, `+tag`, `-tag`, `+area`, `-area` etc
- New transition: Convert whole project to references
- Email inbox: SPF/DKIM verification (IMAP polling via `imaps://` DSN is implemented)
- Add custom *rrule* JS picker <https://demo.mobiscroll.com/vue/scheduler/recurring-events>
- DateTime picker could respect the user's locale.
- htmx show connectivity issue and 500.
- Allow checking item to archive them
- Delete archived item automatically after 30 days ?
- Create a site.webmanifest with a PWA page to add a new task

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
| `CACHE_URL` | `redis://127.0.0.1:6379/1` | Redis cache (production settings only) |
| `STORAGE_URL` | `file://media` | Document storage: `file://<dir>` or `s3://key:secret@endpoint/bucket/prefix?region=...` |
| `DOCUMENT_PRESIGNED_URL_EXPIRY` | `300` | Expiry (seconds) of S3 presigned download URLs |
| `EMAIL_URL` | `console://` | Outgoing email backend DSN (dj-email-url format) |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | — / `587` / — / — | Outgoing SMTP (production settings only) |
| `EMAIL_INBOX_DSN` | `smtp://0.0.0.0:2525?max_size=10485760` | Incoming mail engine DSN, see [Email inbox](#email-inbox) |
| `USER_EMAIL_INBOX_DOMAIN` | `tasks.docker.test` | Domain part of per-user inbox addresses |
| `FRONTEND_URL` | `https://tasks.docker.test` | Public URL of the app |
| `CELERI_ADMIN_URL` | `http://tasks-celery-admin.docker.test/` | Flower dashboard URL |
| `IS_DEMO` | `True` | Show demo credentials on the login page |
| `CUSTOM_AUTHENTICATION_BACKEND` | `""` | Set to `authcrunch` to authenticate via the reverse proxy |
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
?domain_in_username=@constantin.dev  # → inbox-x@constantin.dev
?domain_in_username=constantin.dev   # → inbox-x@constantin.dev  (same thing)
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
You can configure django to use the reverse proxy for authentication.
* Set `CUSTOM_AUTHENTICATION_BACKEND=authcrunch` in your docker-compose.override.yaml file and restart your containers.
* Configure your reverse proxy to set the `X-Token-User-Name` and `X-Token-User-Roles` so that django can identify the user.
* You need a role "authp/admin" to be super-admin.
