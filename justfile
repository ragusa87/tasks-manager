export BACKEND_CONTAINER := "web"

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
  docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py "$@"

# Run manage.py shell_plus
alias shell := shell_plus
alias sp := shell_plus
shell_plus *args:
  docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py shell_plus "$@"

alias t := test
# Run the tests suite
test *args:
  docker compose exec {{BACKEND_CONTAINER}} uv run pytest "$@"

alias validate := lint
alias l := lint
# Lint the code
lint:
  docker compose exec {{BACKEND_CONTAINER}} uv run ruff check

alias fix := format
# Fix styling offenses and format code
format:
  docker compose exec {{BACKEND_CONTAINER}} uv run ruff check --fix

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
  docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py makemigrations "$@"

alias m := migrate
# Migrate the database
migrate:
  docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py migrate

alias f := fixturize
# Reset the database and load the fixtures
fixturize *args:
  docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py fixturize -y "$@"

alias messages := translate
# Make messages and compile them
translate:
	docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py makemessages -a -i "node_modules/*"
	docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py makemessages -a -d djangojs -i "node_modules/*" -i "static/*"
	docker compose exec {{BACKEND_CONTAINER}} uv run python manage.py compilemessages

uv *args:
    docker compose run --rm {{BACKEND_CONTAINER}} uv "$@"

sprites:
    ./sprites/all-gen.sh
import? 'override.justfile'

