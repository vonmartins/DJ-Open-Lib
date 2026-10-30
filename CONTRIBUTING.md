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

## Documentation

The documentation site is built from `docs/` with [Zensical](https://zensical.org).
Preview it while you write:

```sh
uv run --group docs zensical serve
```

CI builds it with `uv run --group docs zensical build --strict`, which fails on a
broken link or a Python name that does not exist. `tests/unit/test_docs.py` checks the
rest: every page is in the `nav` of `mkdocs.yml`, every JSON format and error code is
documented, and the commands in examples exist.

`docs/reference/cli.md` is generated from the commands. After changing a command's
help, arguments or options, regenerate it:

```sh
uv run typer djlib.cli utils docs --name djlib --title Commands --output docs/reference/cli.md
```

A change to a `--json` document, an error code or a public Python name needs its
reference page updated in the same pull request.

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
