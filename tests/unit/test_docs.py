"""The documentation site stays in step with the code (specs/documentation)."""

import ast
import inspect
import itertools
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer.main
import yaml
from typer.testing import CliRunner

import tunedex
from tunedex.cli import app
from tunedex.cli._flow import ERROR_CODES, fail
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Playlist
from tunedex.model.track import Track
from tunedex.store import Store

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

CLI_REFERENCE = DOCS / "reference" / "cli.md"
JSON_REFERENCE = DOCS / "reference" / "json.md"
ERRORS_REFERENCE = DOCS / "reference" / "errors.md"
REGENERATE_CLI = [
    "typer", "tunedex.cli", "utils", "docs",
    "--name", "tunedex", "--title", "Commands", "--output", "docs/reference/cli.md",
]  # fmt: skip


def test_command_reference_matches_the_commands(tmp_path: Path) -> None:
    generated = tmp_path / "cli.md"
    argv = [sys.executable, "-m", *REGENERATE_CLI[:-1], str(generated)]
    subprocess.run(argv, capture_output=True, check=True)

    committed = CLI_REFERENCE.read_text(encoding="utf-8")
    assert generated.read_text(encoding="utf-8") == committed, (
        "docs/reference/cli.md is out of date; regenerate it with: uv run "
        + " ".join(REGENERATE_CLI)
    )


def test_python_api_page_lists_every_public_name() -> None:
    page = (DOCS / "reference" / "python-api.md").read_text(encoding="utf-8")
    documented = re.findall(r"^::: tunedex\.(\w+)$", page, flags=re.MULTILINE)

    assert len(documented) == len(set(documented))
    assert set(documented) == set(tunedex.__all__)


@pytest.mark.parametrize("name", tunedex.__all__)
def test_public_name_has_its_own_docstring(name: str) -> None:
    assert _own_docstring(name, getattr(tunedex, name))


def _own_docstring(name: str, obj: object) -> str | None:
    if inspect.isclass(obj):
        doc = vars(obj).get("__doc__")
        # A dataclass without a docstring gets its signature as one.
        return None if doc is None or doc.startswith(f"{name}(") else doc
    if inspect.isfunction(obj):
        return obj.__doc__
    # A type alias: the string literal under its assignment, as mkdocstrings reads it.
    for path in (ROOT / "src" / "tunedex").rglob("*.py"):
        body = ast.parse(path.read_text(encoding="utf-8")).body
        for statement, following in itertools.pairwise(body):
            if (
                isinstance(statement, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets)
                and isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
            ):
                return following.value.value
    return None


# Navigation


def _nav_pages(entries: list[Any]) -> Iterator[str]:
    for entry in entries:
        for value in entry.values() if isinstance(entry, dict) else [entry]:
            if isinstance(value, list):
                yield from _nav_pages(value)  # pyright: ignore[reportUnknownArgumentType]
            else:
                yield str(value)


def test_every_page_is_in_the_navigation() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    in_nav = list(_nav_pages(config["nav"]))
    on_disk = {p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md")}

    assert len(in_nav) == len(set(in_nav))
    assert set(in_nav) == on_disk


# JSON formats and errors


def _json_formats_in_code() -> set[str]:
    """Every ``tunedex-...`` document name assigned to a ``*FORMAT`` constant."""
    found: set[str] = set()
    for path in (ROOT / "src" / "tunedex").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id.endswith("FORMAT") for t in node.targets)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and node.value.value.startswith("tunedex-")
            ):
                found.add(node.value.value)
    return found


def json_sections() -> dict[str, str]:
    """The text of each ``## `tunedex-...` `` section of the JSON reference, by format."""
    page = JSON_REFERENCE.read_text(encoding="utf-8")
    parts = re.split(r"^## `(tunedex-[a-z]+)`$", page, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def json_example(section: str) -> dict[str, Any]:
    """The first JSON example of a section."""
    found = re.search(r"```json\n(.*?)```", section, flags=re.DOTALL)
    assert found is not None
    return json.loads(found.group(1))


def test_every_json_format_is_documented() -> None:
    formats = _json_formats_in_code()

    assert len(formats) >= 8
    assert set(json_sections()) == formats


def test_json_examples_parse_and_name_their_format() -> None:
    for name, section in json_sections().items():
        version = re.search(r"\*\*Version (\d+)\.\*\*", section)
        example = json_example(section)

        assert version is not None, name
        assert example["format"] == name
        assert example["version"] == int(version.group(1))
    for block in re.findall(
        r"```json\n(.*?)```", ERRORS_REFERENCE.read_text(encoding="utf-8"), re.S
    ):
        json.loads(block)


def _error_codes_in_code() -> set[str]:
    codes = {code for _, code in ERROR_CODES}
    codes.add(inspect.signature(fail).parameters["code"].default)
    for path in (ROOT / "src" / "tunedex" / "cli").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "fail":
                given = node.args[1:2] + [k.value for k in node.keywords if k.arg == "code"]
                codes |= {
                    a.value
                    for a in given
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                }
    return codes


def test_every_error_code_is_documented() -> None:
    page = ERRORS_REFERENCE.read_text(encoding="utf-8")
    table = page.split("## Error codes", 1)[1].split("\n### ", 1)[0]
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", table, flags=re.MULTILINE))

    assert documented == _error_codes_in_code()


# Commands shown in examples


def _example_commands() -> Iterator[tuple[str, str]]:
    """Each ``tunedex ...`` command in a shell code block, with the page it is on."""
    for path in sorted(DOCS.rglob("*.md")):
        if path == CLI_REFERENCE:
            continue
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"```(?:sh|console)\n(.*?)```", text, flags=re.DOTALL):
            for line in block.replace("\\\n", " ").splitlines():
                command = line.removeprefix("$ ").removeprefix("uv run ")
                if re.match(r"([A-Z_]+=\S* )*tunedex\b", command):
                    yield path.relative_to(DOCS).as_posix(), command


def _check_command(line: str) -> None:
    words = shlex.split(line, comments=True)
    while not words[0].startswith("tunedex"):
        words.pop(0)  # environment assignments
    command: Any = typer.main.get_command(app)
    words = words[1:]
    while words:
        word = words.pop(0)
        if word in {"|", ">", "&&", ";"}:
            return
        if word.startswith("-"):
            name = word.split("=", 1)[0]
            option = next((p for p in command.params if name in p.opts + p.secondary_opts), None)
            assert option is not None or name == "--help", f"{name} is not an option"
            if option is not None and not option.is_flag and "=" not in word:
                words.pop(0)
        elif hasattr(command, "commands") and word in command.commands:
            command = command.commands[word]
        else:
            assert not hasattr(command, "commands"), f"{word} is not a command"


def test_example_commands_exist() -> None:
    examples = list(_example_commands())

    assert examples
    for page, line in examples:
        try:
            _check_command(line)
        except AssertionError as error:
            raise AssertionError(f"{page}: {line}: {error}") from None


@pytest.fixture
def small_home(tmp_path: Path) -> Path:
    """A library with a duplicate pair and a folder of two playlists."""
    music = tmp_path / "music"
    music.mkdir()
    tracks: list[Track] = []
    for name, artist, title in (
        ("a.mp3", "Velk", "Rise"),
        ("b.mp3", "Arno", "Glow"),
        ("b copy.mp3", "Arno", "Glow"),
    ):
        (music / name).write_bytes(b"audio")
        tracks.append(Track(path_origin=str(music / name), artist=artist, title=title))
    home = tmp_path / "home"
    home.mkdir()
    with Store.open(home / "library.db") as store:
        store.replace_library(
            Library(
                tracks={t.id: t for t in tracks},
                playlists=(
                    Folder(
                        name="Sets",
                        children=(
                            Playlist(name="Friday", entries=(tracks[0].id,)),
                            Playlist(name="Saturday", entries=(tracks[1].id,)),
                        ),
                    ),
                ),
            )
        )
    return home


def test_json_examples_have_the_fields_of_the_real_output(small_home: Path, tmp_path: Path) -> None:
    runner = CliRunner()

    def document(*arguments: str) -> dict[str, Any]:
        result = runner.invoke(app, ["--home", str(small_home), *arguments, "--json"])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    out = str(tmp_path / "out")
    real = [
        document("export", "m3u", out, "--apply", "--yes"),
        document("status"),
        document("list"),
        document("show", str(tmp_path / "music" / "a.mp3")),
        document("playlists"),
        document("dupes"),
    ]
    snapshots = document("snapshot", "list")
    snapshot = snapshots["snapshots"][0]
    real += [
        snapshots,
        document("snapshot", "restore", snapshot["target"], snapshot["id"], "--apply", "--yes"),
    ]
    sections = json_sections()

    assert {d["format"] for d in real} == set(sections)
    for actual in real:
        example = json_example(sections[actual["format"]])
        assert example["version"] == actual["version"], actual["format"]
        assert list(example) == list(actual), actual["format"]
