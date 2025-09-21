### TODOS
- Reminders & recurring reminders
- Project/Reference views with Hierarchy
- Rename `parent_project` and `project_depth` as it's also used for references.
- Tests & Pipeline
- Add "tags" and import them from nirvana.
- Use select2 for forms autocompletion
- UI for Nirvana import
- Better forms, add missing fields (Energy)
- Priority is always Normal from nirvana. Normal ?
- Dashboard save url
- External JS with vite
### Linting and Formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`
