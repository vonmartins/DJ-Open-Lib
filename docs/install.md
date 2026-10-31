# Install

tunedex needs Python 3.11 or later and runs on Linux, macOS and Windows.

Install it as a command-line tool, isolated from your other Python packages:

=== "uv"

    ```sh
    uv tool install tunedex
    ```

=== "pipx"

    ```sh
    pipx install tunedex
    ```

Check that it works:

```console
$ tunedex --version
```

To upgrade later, run `uv tool upgrade tunedex` or `pipx upgrade tunedex`.

!!! note "The development version"
    Releases come from [PyPI](https://pypi.org/project/tunedex/). To try what is coming next, install the `dev` branch instead: `uv tool install git+https://github.com/vonmartins/tunedex@dev`. It passes every check, but it is not released yet.

## Optional: `fpcalc` for `enrich`

[`tunedex enrich`](guides/enrich.md) recognizes tracks by their sound. It needs `fpcalc` from Chromaprint on your `PATH`:

| System | Command |
|---|---|
| Arch Linux | `pacman -S chromaprint` |
| Debian, Ubuntu | `apt install libchromaprint-tools` |
| macOS | `brew install chromaprint` |
| Windows | Download it from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) |

Nothing else needs `fpcalc`.

## Next

Follow the [tutorial](tutorial.md).
