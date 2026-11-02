# Contributing to Ryujin

Thank you for your interest in contributing to Ryujin! We welcome contributions to make Ryujin the best open-source community bot and management API for Discord.

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment with Python 3.12:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   source .venv/bin/activate # Linux/macOS
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in mock or real credentials.

## Testing Guidelines

Before opening a pull request, ensure all tests pass:
```bash
pytest -v
```

If you add new modules or API endpoints:
- Add business logic to `services/`, not directly in cogs or routers.
- Add corresponding unit and integration tests under `tests/`.
- Ensure new endpoints are covered in `API_REFERENCE.md`.

## Commit Conventions

We follow conventional commit formatting:
- `feat:` for new features
- `fix:` for bug fixes
- `test:` for test additions/improvements
- `docs:` for documentation updates
- `refactor:` for code refactoring without behavior changes

## Pull Request Process

1. Open a PR against the `main` branch.
2. Provide a clear description of the problem solved and changes made.
3. Verify that CI test checks pass.
