"""Hypothesis strategies for track text: any script, plus the dirt fixes look for."""

from hypothesis import strategies as st

# Any printable character of any script; controls and surrogates are not valid tags.
CHARACTERS = st.characters(exclude_categories=("Cc", "Cs", "Co", "Cn"))

DIRT = (
    "https://example.com/track?id=1",
    "www.example.org",
    " (freebeats.com)",
    " [aB3x-9Kq_Zt]",
    "_",
    "__",
    "  ",
    "\u00a0",
    "\u3000",
    "\uff1a",
    "\uff01",
    "Ã©",
    "â€™",
    "&amp;",
    "&#39;",
    "01 - ",
    "1. ",
    " feat. Guest",
    " (ft. Other)",
    " (Tom Ray Remix)",
    " [Rmx]",
    " - ",
    " ",
)

words = st.text(CHARACTERS, min_size=1, max_size=12)
clean_text = st.lists(words, min_size=1, max_size=6).map(" ".join)
dirty_text = st.lists(st.one_of(words, st.sampled_from(DIRT)), min_size=1, max_size=10).map("".join)
