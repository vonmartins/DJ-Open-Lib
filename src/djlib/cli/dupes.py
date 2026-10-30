"""``djlib dupes``: find tracks that are the same song, and merge them into the best one."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

import typer

from djlib.cli import _console, _flow, _options, _paths
from djlib.cli._console import Line
from djlib.cli._flow import fail, home_of, reported_errors, run
from djlib.model.paths import normalize_path
from djlib.model.unmapped import JSONValue
from djlib.planning import Engine, Plan
from djlib.planning.deduplicating import Copy, Decision, Group, GroupKey
from djlib.planning.render import file_size, text_value

JSON_FORMAT = "djlib-dupes"
JSON_VERSION = 1
_ANSWERS = (
    "Enter keeps the marked track, a number keeps that one, s skips the group,"
    " i marks it as not duplicates, q stops asking"
)


def dupes(
    ctx: typer.Context,
    merge: Annotated[
        bool, typer.Option("--merge", help="Plan merging each group into one track.")
    ] = False,
    keep: Annotated[
        list[Path] | None,
        typer.Option(
            "--keep", help="Keep this track in its group (repeatable).", show_default=False
        ),
    ] = None,
    skip: Annotated[
        list[Path] | None,
        typer.Option(
            "--skip",
            help="Leave the group of this track unmerged (repeatable).",
            show_default=False,
        ),
    ] = None,
    ignore: Annotated[
        list[Path] | None,
        typer.Option(
            "--ignore",
            help="Mark the group of this track as not duplicates (repeatable).",
            show_default=False,
        ),
    ] = None,
    keep_files: Annotated[
        bool,
        typer.Option("--keep-files", help="Merge in the library only; move no file to the trash."),
    ] = False,
    under: Annotated[
        Path | None,
        typer.Option(
            "--under", help="Only the groups with a track under this folder.", show_default=False
        ),
    ] = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Report tracks that are the same song, and suggest which one to keep.

    With --merge --apply, asks about each group, then shows one plan: the kept track takes
    the others' tags, cues, playlists and plays, and their files go to the system trash.
    --keep, --skip and --ignore answer for a group without asking.

    Example: djlib dupes --merge --keep ~/Music/a.flac --apply
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
    if not merge:
        with reported_errors(as_json), home_of(ctx).engine() as engine:
            groups = engine.find_duplicates(under=folder)
        if as_json:
            typer.echo(json.dumps(_report_json(groups), ensure_ascii=False, indent=2))
        else:
            _console.echo_lines(_report_text(groups))
        return
    answers: list[tuple[str, Decision | Literal["keep"]]] = [
        *((_track_path(p), "keep") for p in keep or ()),
        *((_track_path(p), "skip") for p in skip or ()),
        *((_track_path(p), "ignore") for p in ignore or ()),
    ]
    interactive = apply and not yes and not as_json and _flow.stdin_is_interactive()

    def make_plan(engine: Engine) -> Plan:
        groups = engine.find_duplicates(under=folder)
        decisions = _decided(groups, answers)
        if interactive:
            decisions = _ask(groups, decisions)
        return engine.plan_merge(decisions, keep_files=keep_files, under=folder)

    run(ctx, make_plan, apply=apply, yes=yes, as_json=as_json)


def _track_path(path: Path) -> str:
    return normalize_path(str(_paths.file(path)))


def _decided(
    groups: Sequence[Group], answers: Sequence[tuple[str, Decision | Literal["keep"]]]
) -> dict[GroupKey, Decision]:
    """The decisions --keep, --skip and --ignore give, by group."""
    decisions: dict[GroupKey, Decision] = {}
    for path, answer in answers:
        found = [(g, c) for g in groups for c in g.copies if c.track.path == path]
        if not found:
            fail(f"{path} is in no group of duplicates", "not_found")
        group, copy = found[0]
        decision = copy.track.id if answer == "keep" else answer
        if decisions.get(group.key, decision) != decision:
            fail(f"the group {group.name!r} has two different answers")
        decisions[group.key] = decision
    return decisions


def _ask(groups: Sequence[Group], kept: dict[GroupKey, Decision]) -> dict[GroupKey, Decision]:
    decisions = dict(kept)
    noun = "group" if len(groups) == 1 else "groups"
    typer.echo(f"{len(groups)} {noun} of duplicates. {_ANSWERS}.")
    for index, group in enumerate(groups, start=1):
        given = kept.get(group.key)
        default = group.copies[0].track.id if given in (None, "skip", "ignore") else given
        number = next(i for i, c in enumerate(group.copies, start=1) if c.track.id == default)
        typer.echo("")
        _console.echo_lines(
            [
                (f"Group {index}/{len(groups)}: {group.name}", "heading"),
                *_copy_lines(group, chosen=default),
            ]
        )
        choices = "/".join(str(i) for i in range(1, len(group.copies) + 1))
        suggested = {"skip": "s", "ignore": "i"}.get(str(given), str(number))
        while True:
            answer = typer.prompt(
                f"Keep [{suggested}] {choices}, s, i, q", default="", show_default=False
            )
            answer = answer.strip().lower()
            if answer == "":
                decisions[group.key] = given if given in ("skip", "ignore") else default
            elif answer.isdigit() and 1 <= int(answer) <= len(group.copies):
                decisions[group.key] = group.copies[int(answer) - 1].track.id
            elif answer in ("s", "i"):
                decisions[group.key] = "skip" if answer == "s" else "ignore"
            elif answer == "q":
                for rest in groups[index - 1 :]:
                    decisions[rest.key] = "skip"
                return decisions
            else:
                typer.echo(_ANSWERS)
                continue
            break
    typer.echo("")
    return decisions


def _report_text(groups: Sequence[Group]) -> list[Line]:
    if not groups:
        return [("No duplicates.", None)]
    lines: list[Line] = [
        (f"Duplicates: {len(groups)} group{'' if len(groups) == 1 else 's'}", "heading")
    ]
    for group in groups:
        lines.append((f"{group.name}  (keep 1: {group.reason})", "heading"))
        lines.extend(_copy_lines(group, chosen=group.copies[0].track.id))
    lines.append(("Run with --merge to plan merging them.", "notice"))
    return lines


def _copy_lines(group: Group, *, chosen: Decision) -> list[Line]:
    """One line per copy, in columns; the chosen one marked with ``*``."""
    rows = [
        (str(i), "*" if c.track.id == chosen else " ", *_details(c), c.track.path)
        for i, c in enumerate(group.copies, start=1)
    ]
    kinds = [
        "chosen" if c.track.id == chosen else None if c.present else "missing" for c in group.copies
    ]
    return list(zip(_console.columns(rows, indent="  "), kinds, strict=True))


def _details(copy: Copy) -> tuple[str, ...]:
    track = copy.track
    kind = (track.file_format or "?").upper()
    rate = f"{track.bitrate} kbps" if track.bitrate else "? kbps"
    length = text_value("duration_us", track.duration_us)
    cues = f"{len(track.cues)} cues"
    playlists = f"{copy.playlists} playlist" + ("" if copy.playlists == 1 else "s")
    size = "missing"
    if copy.present:
        try:
            size = file_size(Path(track.path_origin).stat().st_size)
        except OSError:
            size = "?"
    return kind, rate.rjust(9), length.rjust(5), cues, playlists, size


def _report_json(groups: Sequence[Group]) -> dict[str, JSONValue]:
    return {
        "format": JSON_FORMAT,
        "version": JSON_VERSION,
        "groups": [
            {
                "name": group.name,
                "reason": group.reason,
                "tracks": [
                    {
                        "track_id": str(c.track.id),
                        "path": c.track.path,
                        "format": c.track.file_format,
                        "bitrate": c.track.bitrate,
                        "duration_us": c.track.duration_us,
                        "cues": len(c.track.cues),
                        "playlists": c.playlists,
                        "present": c.present,
                        "suggested": i == 0,
                    }
                    for i, c in enumerate(group.copies)
                ],
            }
            for group in groups
        ],
    }
