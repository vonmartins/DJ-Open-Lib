# Rules

`tunedex fix` cleans tags with bundled **fixes** and your own **rules**. Both change only tunedex's library. Audio files are never touched, and later scans and imports keep the fixed values. Every change in the plan says which fix or rule made it.

The same **conditions** also filter `tunedex list --where`.

## Where the rules come from

1. The file given with `--rules FILE`.
2. Otherwise, `rules.yaml` in the [tunedex home](environment.md#the-home-directory), when it exists.
3. Otherwise, the bundled fixes with their defaults.

`--only NAME` limits a run to some fixes or rule ids. It is repeatable, or takes names separated by commas.

## Fixes

Fixes run in this order, each one seeing the result of the previous ones:

| Fix | What it does | Default fields | On by default |
|---|---|---|---|
| `title_from_file_name` | Fills a missing title, and artist, from `Artist - Title.mp3`. Also restores a title cut at 30 characters (ID3v1) when the file name holds the whole of it. | `title`, `artist` | yes |
| `fix_encoding` | Repairs `CafÃ©` → `Café` and `&amp;` → `&`. | every text field | yes |
| `normalize_characters` | Full-width `：` → `:` outside CJK text; odd and repeated spaces. | every text field | yes |
| `remove_urls` | `Glue (freebeats.com)` → `Glue`; also `http…`, `www.…` and a domain at the end (`Glue my-free-mp3s.com`). | `title`, `artist`, `album` | yes |
| `remove_video_ids` | `Glue [dOFq-swCWro]` → `Glue`. | `title` | yes |
| `underscores_to_spaces` | `Sunrise_Overlook_320` → `Sunrise Overlook 320`. Underscores inside a URL or a domain are kept. | `title`, `album` | yes |
| `remove_leading_number` | `03 - Glue` → `Glue`; also a store id, `1156882 Glue` → `Glue`. | `title` | yes |
| `split_artist_title` | With no artist, `Sam Paganini - Galaxy` → artist `Sam Paganini`, title `Galaxy`, when the file name starts with the same `Sam Paganini - `. | `artist`, `title` | yes |
| `extract_featured` | `Storm (feat. Mira)` or `Storm feat Mira` → title `Storm`, artist `… feat. Mira`. | `title`, `artist` | yes |
| `extract_remixer` | Fills the remixer from `(Tom Ray Remix)`; the title is unchanged. | `remixer` | yes |
| `remove_itunes_data` | Clears a comment that only holds iTunes volume data (`00000EC8 00000EC8 …`). | `comment` | yes |
| `fix_case` | `whisper of the trees` → `Whisper of the Trees`. | `title`, `album` | no: one-case titles are often deliberate (`HUMBLE.`, `bad guy`) |

## The rules file

A rules file has two optional sections, `fixes` and `rules`:

```yaml
fixes:
  extract_featured: false        # turn a fix off
  remove_urls:
    fields: [title, comment]     # change which fields it cleans
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

### `fixes`

Each entry maps a fix's name to one of:

- `false`, to turn the fix off;
- `true`, to turn it on with its defaults;
- its options:
    - `fields`, a list of text fields, for the fixes that clean any field (`fix_encoding`, `normalize_characters`, `remove_urls`, `remove_video_ids`, `underscores_to_spaces`, `fix_case`);
    - `keep`, for `fix_case`: words to keep exactly as written.

A fix the file does not name keeps its default.

### `rules`

Rules run after the fixes, in file order. Each rule has:

| Key | Meaning |
|---|---|
| `id` | A name for the rule. It is shown in the plan and accepted by `--only`. |
| `when` | One [condition](#conditions) or a list of them. |
| `match` | `all` (the default) or `any`: whether every condition or at least one must hold. |
| `then` | One action or a list of them. |

The actions are:

- `{replace: FIELD, pattern: REGEX, with: TEXT}` replaces every match of the regular expression in a text field. `with` can use the pattern's groups as `\1`.
- `{set: FIELD, value: VALUE}` sets a field. An empty value clears it.

If a value does not fit the field, such as text for `bpm`, that rule leaves the track unchanged and the plan shows a warning.

Running the same fixes and rules again on their result changes nothing.

## Conditions

A condition names a `field`, an `op` and, for most operators, a `value` (or `values` for `in`):

```yaml
{field: bpm, op: gte, value: 170}
{field: genre, op: in, values: [Techno, House]}
{field: comment, op: empty}
```

`field` is any [track field](json.md#track), such as `title`, `bpm`, `key`, `date_added` or `tags`.

| Field type | Operators |
|---|---|
| Text | `equals`, `not_equals`, `contains`, `not_contains`, `starts_with`, `ends_with`, `in`, `matches` |
| Numbers and dates | `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in` |
| Any | `empty`, `not_empty` |

- Text comparisons ignore case, except `matches`, which takes a regular expression.
- A condition on an empty field is false for every operator except `empty`, `not_equals` and `not_contains`.

An unknown fix, field, operator, option or action, or an invalid regular expression, is an `invalid_rule` error that names the rule. Nothing is planned.

## `--where`

`tunedex list --where` takes conditions as short `FIELD OP VALUE` expressions:

| Operator | Means |
|---|---|
| `=` | `equals` |
| `!=` | `not_equals` |
| `~` | `contains` |
| `!~` | `not_contains` |
| `>` `>=` `<` `<=` | `gt` `gte` `lt` `lte` |

```sh
tunedex list --where "genre=Techno" --where "bpm>=130"
tunedex list --where "title~remix"
tunedex list --where "comment="
```

- `FIELD=` with no value matches an empty field, and `FIELD!=` matches a field with a value.
- On `tags`, `=` and `!=` mean contains and does not contain.
- `--where` is repeatable, and every condition must hold.
