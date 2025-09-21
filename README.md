### TODOS
- Reminders
- Project/Reference view with Hierarchy
- Rename `parent_project` and `project_depth` as it's also used for references.
- Tests & Pipeline

### Linting and Formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`
