### TODOS
- Reminders & recurring reminders
- Project/Reference views with Hierarchy
- Rename `parent_project` and `project_depth` as it's also used for references.
- Tests & Pipeline
- Use select2 for forms autocompletion
- Nirvana: UI for import, `tag<->area` conversion
- Better forms, add missing fields
- Priority is always Normal from nirvana. Normal ?
- External JS with vite + tailwind - https://tailwindcss.com/docs/installation/using-vite
- Convert whole project to references

### Linting and Formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Settings

- **Development**: `core.settings.development`
- **Testing**: `core.settings.test` (auto-selected when running tests)
- **Production**: `core.settings.production`
