### TODOS
- Tests & Pipeline
- Use select2 for forms autocompletion
- Nirvana: UI for import, fix importing reference (parent reference is currently a project instead of a reference)
- Bach actions support: `tag<->area` conversion, `+tag`, `-tag`, `+area`, `-area` etc
- New transition: Convert whole project to references
- Email inbox via https://maileroo.com/docs/inbound-routing/
- Add Hierarchy in view
### Linting and Formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`
