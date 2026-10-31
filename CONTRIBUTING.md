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
uv run typer tunedex.cli utils docs --name tunedex --title Commands --output docs/reference/cli.md
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

## Releasing

Releases are published by the `Release` workflow, never from a computer. PyPI accepts
each version once, so rehearse first.

1. On a branch from `dev`, set the version with `uv version X.Y.Z` (it updates
   `uv.lock` too), and rename the CHANGELOG's `Unreleased` section to
   `[X.Y.Z] - YYYY-MM-DD`, with an empty `Unreleased` above it and the comparison links
   at the bottom. `uv run python scripts/release_check.py X.Y.Z` prints the notes the
   release will get. Merge the pull request into `dev`.
2. Rehearse: run the `Release` workflow by hand on `dev` (Actions → Release → Run
   workflow). It builds the package, tests the wheel on Linux, macOS and Windows, and
   publishes it to [TestPyPI](https://test.pypi.org/project/tunedex/).
3. Open a pull request from `dev` to `main` and merge it with a merge commit, not a
   squash, so that `dev` stays a descendant of `main`. Merging publishes the
   documentation site.
4. Tag the merge commit on `main` and push the tag:

   ```sh
   git switch main && git pull
   git tag -a vX.Y.Z -m "tunedex X.Y.Z"
   git push origin vX.Y.Z
   ```

   The workflow checks that the tag is on `main` and matches the version, builds and
   tests the package, publishes it to PyPI through trusted publishing (no token is
   stored anywhere), creates the GitHub release with the CHANGELOG notes, and installs
   the release from PyPI on the three systems.

If a broken version reaches PyPI, yank it there and release a patch version.
