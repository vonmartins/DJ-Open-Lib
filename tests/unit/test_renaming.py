import pytest

from tunedex.model.key import Key, Mode
from tunedex.model.track import Track
from tunedex.renaming import DEFAULT_PATTERN, Missing, PatternError, parse_pattern, safe_name

TRACK = Track(path_origin="/music/dl/x.mp3", artist="Sam Paganini", title="Galaxy")


def name(track: Track, pattern: str = DEFAULT_PATTERN, extension: str = ".mp3") -> str | None:
    stem = parse_pattern(pattern).format(track)
    assert isinstance(stem, str), stem
    return safe_name(stem, extension)


def test_default_pattern() -> None:
    assert name(TRACK) == "Sam Paganini - Galaxy.mp3"


def test_optional_part() -> None:
    pattern = "{artist} - {title}{ (remixer remix)}"
    remixed = Track(path_origin="/m/a.mp3", artist="Bicep", title="Glue", remixer="Scuba")
    plain = Track(path_origin="/m/b.mp3", artist="Bicep", title="Glue")
    assert name(remixed, pattern) == "Bicep - Glue (Scuba remix).mp3"
    assert name(plain, pattern) == "Bicep - Glue.mp3"


def test_formats_of_numbers_and_keys() -> None:
    track = Track(
        path_origin="/m/a.flac",
        artist="Bicep",
        title="Glue",
        year=2017,
        bpm=127.6,
        key=Key(tonic=9, mode=Mode.MINOR),
        track_number=3,
    )
    pattern = "{track_number} {artist} - {title} [{year}] {bpm} {key}"
    assert name(track, pattern, ".flac") == "03 Bicep - Glue [2017] 128 1m.flac"


def test_missing_field() -> None:
    track = Track(path_origin="/m/a.mp3", title="Galaxy")
    assert parse_pattern(DEFAULT_PATTERN).format(track) == Missing("artist")


@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("{artist} - {name}", "unknown field 'name'"),
        ("{artist} - {title", "without"),
        ("artist} - {title}", "without"),
        ("{ (foo remix)}", "exactly one field"),
        ("{ (remixer mix)}", "exactly one field"),
        ("{{title}}", "nested"),
        ("no fields", "has no field"),
        ("{}", "exactly one field"),
    ],
)
def test_bad_patterns(pattern: str, message: str) -> None:
    with pytest.raises(PatternError, match=message):
        parse_pattern(pattern)


def test_forbidden_characters() -> None:
    track = Track(path_origin="/m/a.mp3", artist="AC/DC", title="Who: Made Who?")
    assert name(track) == "AC_DC - Who - Made Who_.mp3"


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ('a\\b*c?"d<e>f|g', "a_b_c__d_e_f_g.mp3"),
        ("tab\there", "tab_here.mp3"),
        ("  spaced   out  ", "spaced out.mp3"),
        ("ends with dots...", "ends with dots.mp3"),
        ("CON", "CON_.mp3"),
        ("com1", "com1_.mp3"),
        ("NUL.remix", "NUL_.remix.mp3"),
        ("CONTROL", "CONTROL.mp3"),
        ("...", None),
        # Names from a real collection.
        ("Conformal - Tåglek", "Conformal - Tåglek.mp3"),
        (
            "Zombie Nation (Hardtrance Remix) - Zoinks",
            "Zombie Nation (Hardtrance Remix) - Zoinks.mp3",
        ),
        ("Âme - Rej (Original Mix)", "Âme - Rej (Original Mix).mp3"),
        ("DJ Koze - XTC: Edit", "DJ Koze - XTC - Edit.mp3"),
    ],
)
def test_safe_names(stem: str, expected: str | None) -> None:
    assert safe_name(stem, ".mp3") == expected


def test_decomposed_names_are_composed() -> None:
    assert safe_name("Åme", ".mp3") == "Åme.mp3"


def test_long_names_are_cut_to_255_bytes() -> None:
    cut = safe_name("é" * 300, ".flac")
    assert cut is not None
    assert len(cut.encode()) <= 255
    assert cut.endswith(".flac")
    assert cut.startswith("é")


def test_the_extension_is_kept() -> None:
    assert safe_name("Galaxy", ".MP3") == "Galaxy.MP3"
