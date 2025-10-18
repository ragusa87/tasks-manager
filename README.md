### Disclamer

This is a pet projet, goal is to do some code-flow with IA. 
I don't intent to maintain this project in the long term.

### TODOS
- Tests & Pipeline
- Nirvana: UI for import, fix importing reference (parent reference is currently a project instead of a reference)
- Bach actions support: `tag<->area` conversion, `+tag`, `-tag`, `+area`, `-area` etc
- New transition: Convert whole project to references
- Email inbox via https://maileroo.com/docs/inbound-routing/
- Add custom *rrule* JS picker.
- New views/action: `create a new project` , `delete an area`, `delete a tag` 
- DateTime picker could respect the user's locale.
- htmx show connectivity issue and 500.

### Linting and Formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`


### Setup

Requirements:
- docker & docker-compose
- traefik (optional, only if you want to use it as reverse-proxy)
- justfile (optional)

#### Initialize the project 
```bash
./bin/init.sh
```
The command above will create a docker-compose.override.yaml file for you (based on docker-compose.override.example.yaml).

WARNING: If you re-run the command again, all existing data in your database will be lost!
