# Fixing tags with rules

`tunedex fix` cleans the tags of the library with bundled fixes and your own rules.

```sh
tunedex fix                                       # show what would change
tunedex fix --apply
tunedex fix --only remove_urls,extract_featured   # only some fixes
tunedex fix --under ~/Music/New                   # only some tracks
```

Every change in the plan says which fix or rule made it:

```text
  ~ Benga - E Trips [6U6S6iXLSmU]  ~/Music/Benga - E Trips.mp3
      title: 'E Trips [6U6S6iXLSmU]' → 'E Trips'  (remove_video_ids)
```

Only tunedex's library changes. Audio files are never touched, and later scans and imports keep your fixed values.

## The bundled fixes

They remove URLs and video ids from titles, fill missing titles from file names, repair broken characters, move `feat.` guests to the artist and find remixers. All but `fix_case` are on by default. The [rules reference](../reference/rules.md#fixes) lists each one with examples.

## Your own rules

Put a `rules.yaml` in the [tunedex home](../reference/environment.md#the-home-directory), or pass `--rules FILE`. In it you can turn fixes off, tune them, and add rules:

```yaml
fixes:
  extract_featured: false        # keep guests in titles
  fix_case:                      # turn it on, with words to keep as written
    keep: [DJ, MC, SBTRKT]
rules:
  - id: no-year-in-title
    when: {field: title, op: matches, value: ' \[\d{4}\]$'}
    then: {replace: title, pattern: ' \[\d{4}\]$', with: ''}
  - id: one-dnb-genre
    match: any
    when:
      - {field: genre, op: equals, value: DnB}
      - {field: genre, op: equals, value: Drum n Bass}
    then: {set: genre, value: Drum And Bass}
```

A rule says **when** it applies, with one or more conditions, and what it does **then**: replace text or set a field. The [rules reference](../reference/rules.md) has every operator and action.

Keep the file in git if you like: it is your library's cleanup, as code.

## Running it again

Fixes and rules are idempotent: once applied, `tunedex fix` plans nothing until the library or the rules change. A bad rule is an error that names it, and nothing is planned.
