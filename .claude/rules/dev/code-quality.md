# Code Quality Standards

## Pre-commit (runs automatically on `git commit`)

- **black**: Code formatting (line-length=88)
- **ruff**: Linting (rules: E, F, W, I, UP, B, SIM, RUF)
- **mypy**: Type checking (python 3.12, strict optional)
Source of truth for all settings: `pyproject.toml`

Tests are verified via CI and local manual execution (`uv run pytest -m unit`), not pre-commit.

## Manual Commands

```bash
uv run black .                # Format
uv run ruff check .           # Lint
uv run mypy .                 # Type check
uv run pytest                 # All tests
uv run pytest -m unit         # Unit only
```

## Bash Style

- Don't chain commands (`&&`, `||`, `;`) — triggers re-permission prompts
- Use parallel Bash tool calls for independent commands
- Chain only when order-dependent (e.g., `git add && git commit`)
