# Contributing

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs the right Python version
for you.

```sh
uv sync
uv run pre-commit install
```

## Checks

CI runs these on Linux, macOS and Windows. Run them before opening a pull request:

```sh
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest
```

`pre-commit` runs the lint, format and type checks on every commit. Tests run
only in CI and when you run them yourself.

## Safety rule: never touch real DJ libraries

During development, code must never read from or write to the live library of an
installed DJ app (Traktor's `collection.nml`, Rekordbox's database, and so on).
Tests use only the sanitized samples in [`tests/fixtures/`](tests/fixtures/README.md)
and write only to temporary directories.

## Branches

- `main` holds releases only. `dev` is the integration branch and must always
  build and pass the checks.
- Create your branch from `dev` (`feat/...`, `fix/...`, `chore/...`) and open
  the pull request against `dev`.
- A release is a pull request from `dev` to `main`.

## Commits and versions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:` ...).
- Versions follow [Semantic Versioning](https://semver.org/).
- User-visible changes go in [CHANGELOG.md](CHANGELOG.md) under `Unreleased`.
