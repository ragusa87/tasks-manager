export BACKEND_CONTAINER := "web"
export FRONTEND_CONTAINER := "vite"

set allow-duplicate-recipes
set positional-arguments

default:
  just --list

# Run the development server
start *args:
  docker compose up "$@"

# Run bash in backend container
alias exec := bash
bash *args:
  docker compose exec {{BACKEND_CONTAINER}} bash "$@"

alias django := manage
alias dj := manage
# Run a Django manage.py command
manage *args:
  docker compose exec {{BACKEND_CONTAINER}} python manage.py "$@"

# Run manage.py shell_plus
alias shell := shell_plus
alias sp := shell_plus
shell_plus *args:
  docker compose exec {{BACKEND_CONTAINER}} python manage.py shell_plus "$@"

alias t := test
test *args:
  docker compose exec -e DJANGO_SETTINGS_MODULE=core.settings.test {{BACKEND_CONTAINER}} pytest "$@"

alias validate := lint
alias l := lint
# Lint the code
lint:
  docker compose exec {{BACKEND_CONTAINER}} ruff check

alias fix := format
# Fix styling offenses and format code
format:
  docker compose exec {{BACKEND_CONTAINER}} ruff check --fix

alias c := compile
# Compile the requirements files
compile:
  docker compose exec {{BACKEND_CONTAINER}} uv lock

alias i := install
# Install dependencies
install:
  docker compose exec {{BACKEND_CONTAINER}} uv sync

alias mm := makemigrations
# Generate database migrations
makemigrations *args:
  docker compose exec {{BACKEND_CONTAINER}} python manage.py makemigrations "$@"

alias m := migrate
# Migrate the database
migrate:
  docker compose exec {{BACKEND_CONTAINER}} python manage.py migrate

alias f := fixturize
# Reset the database and load the fixtures
fixturize *args:
  docker compose exec {{BACKEND_CONTAINER}} python manage.py fixturize "$@"

npm *args:
  docker compose exec {{FRONTEND_CONTAINER}} npm "$@"

alias messages := translate
# Make messages and compile them
translate:
	docker compose exec {{BACKEND_CONTAINER}} python manage.py makemessages -a -i "node_modules/*"
	docker compose exec {{BACKEND_CONTAINER}} python manage.py makemessages -a -d djangojs -i "node_modules/*" -i "static/*"
	docker compose exec {{BACKEND_CONTAINER}} python manage.py compilemessages

uv *args:
    docker compose run --rm {{BACKEND_CONTAINER}} uv "$@"

sprites:
    @just manage sprites

# Regenerate the README screenshots (docs/img/) from a running instance.
# Destructive — wipes local data (fixturize --clear). Playwright/npx run on the
# HOST (not in Docker); Playwright is auto-provisioned via npx (override with
# PLAYWRIGHT_MODULE if needed).
capture-docs base_url="https://tasks.docker.test":
  just fixturize --clear
  BASE_URL="{{base_url}}" node scripts/capture_docs_screenshots.mjs

# Send a test email to the local mail inbox (from must be a whitelisted sender)
mail-send to from="user1@example.com" subject="Test task" body="Created by just mail-send":
  docker compose exec {{BACKEND_CONTAINER}} python -c "import smtplib, sys; from email.message import EmailMessage; m = EmailMessage(); m['From'] = sys.argv[1]; m['To'] = sys.argv[2]; m['Subject'] = sys.argv[3]; m.set_content(sys.argv[4]); s = smtplib.SMTP('mail', 2525); s.send_message(m); s.quit(); print('sent')" {{quote(from)}} {{quote(to)}} {{quote(subject)}} {{quote(body)}}
import? 'override.justfile'
