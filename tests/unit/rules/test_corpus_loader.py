from pathlib import Path

import pytest

from support.rules_corpus import CorpusError, clean, load


def test_rows_name_their_file_and_index(tmp_path: Path) -> None:
    path = tmp_path / "remove_urls.yaml"
    path.write_text(
        "fix: remove_urls\nchange:\n  - {in: a, out: b, why: ok}\n  - {in: c, out: d}\n"
    )

    with pytest.raises(CorpusError, match=r"remove_urls\.yaml#2 \(change\): every row needs a why"):
        load("remove_urls", path)


def test_change_rows_need_an_expected_value(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("fix: x\nchange:\n  - {track: {title: a}, why: no expected}\n")

    with pytest.raises(CorpusError, match=r"x\.yaml#1 \(change\)"):
        load("x", path)


def test_clean_corpus_is_large_and_varied() -> None:
    tracks = clean()

    assert len(tracks) >= 300
    assert any(t.title and any("぀" <= c <= "ヿ" for c in t.title) for t in tracks)
    assert any(t.artist and any("Ѐ" <= c <= "ӿ" for c in t.artist) for t in tracks)
