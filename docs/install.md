# Install

djlib needs Python 3.11 or later and runs on Linux, macOS and Windows.

Install it as a command-line tool, isolated from your other Python packages:

=== "uv"

    ```sh
    uv tool install git+https://github.com/vonmartins/DJ-Open-Lib
    ```

=== "pipx"

    ```sh
    pipx install git+https://github.com/vonmartins/DJ-Open-Lib
    ```

Check that it works:

```console
$ djlib --version
```

To upgrade later, run `uv tool upgrade djlib` or `pipx upgrade djlib`.

!!! note "Not on PyPI yet"
    Until the first release, djlib installs from the Git repository. After it, `uv tool install djlib` and `pipx install djlib` will work too.

## Optional: `fpcalc` for `enrich`

[`djlib enrich`](guides/enrich.md) recognizes tracks by their sound. It needs `fpcalc` from Chromaprint on your `PATH`:

| System | Command |
|---|---|
| Arch Linux | `pacman -S chromaprint` |
| Debian, Ubuntu | `apt install libchromaprint-tools` |
| macOS | `brew install chromaprint` |
| Windows | Download it from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) |

Nothing else needs `fpcalc`.

## Next

Follow the [tutorial](tutorial.md).
