import pytest

from tunedex.model.errors import ValidationError
from tunedex.model.key import Key, Mode, parse_musical, parse_open_key

ALL_KEYS = [Key(tonic=t, mode=m) for m in Mode for t in range(12)]


def test_spec_examples() -> None:
    assert Key(tonic=9, mode=Mode.MINOR).open_key() == "1m"
    f_sharp_minor = parse_musical("F#m")
    assert f_sharp_minor is not None
    assert f_sharp_minor == Key(tonic=6, mode=Mode.MINOR)
    assert f_sharp_minor.open_key() == "4m"


@pytest.mark.parametrize(
    ("key", "open_key", "musical"),
    [
        (Key(tonic=0, mode=Mode.MAJOR), "1d", "C"),
        (Key(tonic=7, mode=Mode.MAJOR), "2d", "G"),
        (Key(tonic=5, mode=Mode.MAJOR), "12d", "F"),
        (Key(tonic=4, mode=Mode.MINOR), "2m", "Em"),
        (Key(tonic=2, mode=Mode.MINOR), "12m", "Dm"),
        (Key(tonic=10, mode=Mode.MAJOR), "11d", "Bb"),
    ],
)
def test_known_renderings(key: Key, open_key: str, musical: str) -> None:
    assert key.open_key() == open_key
    assert key.musical() == musical


@pytest.mark.parametrize("key", ALL_KEYS, ids=lambda k: k.musical())
def test_every_key_round_trips(key: Key) -> None:
    assert parse_open_key(key.open_key()) == key
    assert parse_musical(key.musical()) == key
    assert Key.from_code(key.code) == key


def test_notations_are_bijective() -> None:
    assert len({k.open_key() for k in ALL_KEYS}) == 24
    assert len({k.musical() for k in ALL_KEYS}) == 24
    assert sorted(k.code for k in ALL_KEYS) == list(range(24))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Gb", Key(tonic=6, mode=Mode.MAJOR)),
        ("C#m", Key(tonic=1, mode=Mode.MINOR)),
        ("Ebm", Key(tonic=3, mode=Mode.MINOR)),
        ("bm", Key(tonic=11, mode=Mode.MINOR)),
        ("E♭ minor", Key(tonic=3, mode=Mode.MINOR)),
        ("F♯min", Key(tonic=6, mode=Mode.MINOR)),
        ("A maj", Key(tonic=9, mode=Mode.MAJOR)),
        ("B#", Key(tonic=0, mode=Mode.MAJOR)),
        (" Am ", Key(tonic=9, mode=Mode.MINOR)),
    ],
)
def test_parse_musical_variants(text: str, expected: Key) -> None:
    assert parse_musical(text) == expected


@pytest.mark.parametrize(("text", "expected"), [("01m", "1m"), ("10D", "10d"), (" 5m", "5m")])
def test_parse_open_key_variants(text: str, expected: str) -> None:
    key = parse_open_key(text)
    assert key is not None
    assert key.open_key() == expected


@pytest.mark.parametrize("text", ["X#q", "", "AM", "H", "Am7", "C##"])
def test_unknown_musical_text(text: str) -> None:
    assert parse_musical(text) is None


@pytest.mark.parametrize("text", ["0m", "13d", "1x", "8A", "1"])
def test_unknown_open_key_text(text: str) -> None:
    assert parse_open_key(text) is None


@pytest.mark.parametrize("tonic", [-1, 12])
def test_tonic_range(tonic: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Key(tonic=tonic, mode=Mode.MAJOR)
    assert excinfo.value.field == "tonic"


@pytest.mark.parametrize("code", [-1, 24])
def test_code_range(code: int) -> None:
    with pytest.raises(ValidationError):
        Key.from_code(code)
