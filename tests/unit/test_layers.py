"""The core library must not depend on its interface layers."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["djlib.model", "djlib.store"])
def test_core_does_not_import_the_cli(module: str) -> None:
    code = (
        f"import sys, {module}, pkgutil, importlib\n"
        f"for info in pkgutil.walk_packages({module}.__path__, '{module}.'):\n"
        "    importlib.import_module(info.name)\n"
        "print(sorted(m for m in sys.modules if m == 'typer' or m.startswith('djlib.cli')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"
