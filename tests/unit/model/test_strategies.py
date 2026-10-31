from hypothesis import given, settings

from support.strategies import libraries, synthetic_library
from tunedex.model.library import Library


@given(libraries())
@settings(max_examples=50)
def test_generated_libraries_are_valid(library: Library) -> None:
    assert Library.build(library.tracks.values(), library.playlists) == library


def test_synthetic_library_is_deterministic() -> None:
    first, second = synthetic_library(200, seed=1), synthetic_library(200, seed=1)

    assert first == second
    assert len(first.tracks) == 200
    assert sum(1 for _ in first.walk()) == 71
