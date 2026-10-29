"""``djlib dupes``: find tracks that are the same song, and merge them into the best one."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _flow, _options
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
    keep_files: Annotated[
        bool,
        typer.Option("--keep-files", help="Merge in the library only; move no file to the trash."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Report tracks that are the same song, and suggest which one to keep.

    With --merge --apply, asks about each group, then shows one plan: the kept track takes
    the others' tags, cues, playlists and plays, and their files go to the system trash.
    """
    if not merge:
        with reported_errors(), home_of(ctx).engine() as engine:
            groups = engine.find_duplicates()
        if as_json:
            typer.echo(json.dumps(_report_json(groups), ensure_ascii=False, indent=2))
        else:
            typer.echo(_report_text(groups), nl=False)
        return
    kept = [normalize_path(str(path.absolute())) for path in keep or ()]
    interactive = apply and not yes and not as_json and _flow.stdin_is_interactive()

    def make_plan(engine: Engine) -> Plan:
        groups = engine.find_duplicates()
        decisions = _kept(groups, kept)
        if interactive:
            decisions = _ask(groups, decisions)
        return engine.plan_merge(decisions, keep_files=keep_files)

    run(ctx, make_plan, apply=apply, yes=yes, as_json=as_json)


def _kept(groups: Sequence[Group], paths: Sequence[str]) -> dict[GroupKey, Decision]:
    decisions: dict[GroupKey, Decision] = {}
    for path in paths:
        found = [(g, c) for g in groups for c in g.copies if c.track.path == path]
        if not found:
            fail(f"{path} is in no group of duplicates")
        group, copy = found[0]
        decisions[group.key] = copy.track.id
    return decisions


def _ask(groups: Sequence[Group], kept: dict[GroupKey, Decision]) -> dict[GroupKey, Decision]:
    decisions = dict(kept)
    noun = "group" if len(groups) == 1 else "groups"
    typer.echo(f"{len(groups)} {noun} of duplicates. {_ANSWERS}.")
    for index, group in enumerate(groups, start=1):
        default = kept.get(group.key, group.copies[0].track.id)
        number = next(i for i, c in enumerate(group.copies, start=1) if c.track.id == default)
        typer.echo(f"\nGroup {index}/{len(groups)}: {group.name}")
        typer.echo("\n".join(_copy_lines(group, chosen=default)))
        choices = "/".join(str(i) for i in range(1, len(group.copies) + 1))
        while True:
            answer = typer.prompt(
                f"Keep [{number}] {choices}, s, i, q", default="", show_default=False
            )
            answer = answer.strip().lower()
            if answer == "":
                decisions[group.key] = default
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


def _report_text(groups: Sequence[Group]) -> str:
    if not groups:
        return "No duplicates.\n"
    lines = [f"Duplicates: {len(groups)} group{'' if len(groups) == 1 else 's'}"]
    for group in groups:
        lines.append(f"{group.name}  (keep 1: {group.reason})")
        lines.extend(_copy_lines(group, chosen=group.copies[0].track.id))
    lines.append("Run with --merge to plan merging them.")
    return "\n".join(lines) + "\n"


def _copy_lines(group: Group, *, chosen: Decision) -> list[str]:
    return [
        f"  {i} {'*' if c.track.id == chosen else ' '} {_details(c)}  {c.track.path}"
        for i, c in enumerate(group.copies, start=1)
    ]


def _details(copy: Copy) -> str:
    track = copy.track
    kind = (track.file_format or "?").upper()
    rate = f"{track.bitrate} kbps" if track.bitrate else "? kbps"
    length = text_value("duration_us", track.duration_us)
    playlists = f"{copy.playlists} playlist" + ("" if copy.playlists == 1 else "s")
    missing = "  missing" if not copy.present else ""
    size = ""
    if copy.present:
        try:
            size = f"  {file_size(Path(track.path_origin).stat().st_size)}"
        except OSError:
            size = ""
    return f"{kind:4} {rate:>9}  {length:>5}  {len(track.cues)} cues  {playlists}{size}{missing}"


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
