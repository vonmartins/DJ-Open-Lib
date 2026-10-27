from collections.abc import Iterator
from pathlib import Path

import pytest

from djlib.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with Store.open(tmp_path / "library.db") as opened:
        yield opened
