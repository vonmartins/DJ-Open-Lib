"""The documentation site stays in step with the code (specs/documentation)."""

import ast
import inspect
import itertools
import re
import subprocess
import sys
from pathlib import Path

import pytest

import djlib

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

CLI_REFERENCE = DOCS / "reference" / "cli.md"
REGENERATE_CLI = [
    "typer", "djlib.cli", "utils", "docs",
    "--name", "djlib", "--title", "Commands", "--output", "docs/reference/cli.md",
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
    documented = re.findall(r"^::: djlib\.(\w+)$", page, flags=re.MULTILINE)

    assert len(documented) == len(set(documented))
    assert set(documented) == set(djlib.__all__)


@pytest.mark.parametrize("name", djlib.__all__)
def test_public_name_has_its_own_docstring(name: str) -> None:
    assert _own_docstring(name, getattr(djlib, name))


def _own_docstring(name: str, obj: object) -> str | None:
    if inspect.isclass(obj):
        doc = vars(obj).get("__doc__")
        # A dataclass without a docstring gets its signature as one.
        return None if doc is None or doc.startswith(f"{name}(") else doc
    if inspect.isfunction(obj):
        return obj.__doc__
    # A type alias: the string literal under its assignment, as mkdocstrings reads it.
    for path in (ROOT / "src" / "djlib").rglob("*.py"):
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
