# Contributing

Thanks for contributing to AOP MCP Server.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
```

## Running tests

```bash
pytest
```

Optional checks:

```bash
make contract
make smoke
```

## Pull request guidelines

1. Keep changes scoped and include tests for behavior changes.
2. Update docs and JSON schemas when tool responses or contracts change.
3. Do not commit secrets, tokens, credentials, or private endpoint data.
4. Prefer fixture-based tests over live network dependencies.
5. Keep commit messages clear and descriptive.

## Commit and review expectations

1. All CI checks must pass.
2. Breaking changes should include migration notes in the PR description.
3. New configuration options must be added to `.env.example` and `README.md`.
