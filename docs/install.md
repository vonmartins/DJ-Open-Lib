# Install

tunedex needs Python 3.11 or later and runs on Linux, macOS and Windows.

Install it as a command-line tool, isolated from your other Python packages:

=== "uv"

    ```sh
    uv tool install git+https://github.com/vonmartins/tunedex
    ```

=== "pipx"

    ```sh
    pipx install git+https://github.com/vonmartins/tunedex
    ```

Check that it works:

```console
$ tunedex --version
```

To upgrade later, run `uv tool upgrade tunedex` or `pipx upgrade tunedex`.

!!! note "Not on PyPI yet"
    Until the first release, tunedex installs from the Git repository. After it, `uv tool install tunedex` and `pipx install tunedex` will work too.

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
