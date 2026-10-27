import pytest

from djlib.adapters.m3u.names import MAX_NAME_BYTES, sanitize, unique


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Drum & Bass: 170/174", "Drum & Bass_ 170_174"),
        ('a<b>c"d|e?f*g\\h', "a_b_c_d_e_f_g_h"),
        ("tab\there", "tab_here"),
        ("Ends with dots...", "Ends with dots"),
        ("Trailing space  ", "Trailing space"),
        ("CON", "CON_"),
        ("con.mix", "con_.mix"),
        ("LPT9", "LPT9_"),
        ("COM10", "COM10"),
        ("...", "_"),
        ("", "_"),
        ("Beyoncé ☀️", "Beyoncé ☀️"),
        ("unassigned \U00014647 x", "unassigned _ x"),
        ("non-character \uffff", "non-character _"),
        ("lone \udc80 surrogate", "lone _ surrogate"),
    ],
)
def test_sanitize(name: str, expected: str) -> None:
    assert sanitize(name) == expected


def test_long_names_truncated_on_character_boundary() -> None:
    result = sanitize("é" * 200)
    assert len(result.encode()) <= MAX_NAME_BYTES
    assert result == "é" * (MAX_NAME_BYTES // 2)


def test_collisions_are_case_insensitive() -> None:
    taken: set[str] = set()
    assert [unique(n, taken) for n in ("Set", "set", "SET", "Other")] == [
        "Set",
        "set (2)",
        "SET (3)",
        "Other",
    ]


def test_suffix_fits_length_limit() -> None:
    long = "x" * MAX_NAME_BYTES
    taken = {long.casefold()}
    result = unique(long, taken)
    assert result.endswith(" (2)") and len(result.encode()) <= MAX_NAME_BYTES
