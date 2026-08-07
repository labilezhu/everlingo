# Single-Language Memory Vault Spec

A memory vault made of markdown files and a structured directory tree. It records the user's language-learning events and language knowledge points.

The `single-language Memory Vault` is also called `language notes library` or `notes library` or `memory library`.

Single-language vault directory structure example:
```bash
spec/ # Memory Vault directory structure spec and knowledge-point file spec. This directory always exists. Before browsing, reading, writing, or searching the vault, read the spec files in it to learn the conventions and terminology.
  vault_spec.md # vault overall structure and file conventions
  events_spec.md # conventions for event files under events/
  kb_items_spec.md # conventions for knowledge-point files under items/
events/
  2026/
    06/
      2026-06-26.md
items/ # knowledge-point memory items (incomplete example)
  vocab/
    gcc.md
    ambiguous.md
  phrase/
    take-for-granted.md
  grammar/
    present-perfect.md
  pragmatics/
  others/
tmp/ # program-internal temporary files with no user-data value. Not indexed
```

## What language should the markdown files be written in

The files are primarily notes read by language learners. Therefore, under default conditions the main language should be the `interface language`. For `target learning language` references — such as the `target language`'s words, example sentences, examples, and terminology — you should use the `target learning language`.

## /events events

Event files are stored under the /events directory.

Before reading or writing any file under `events/` and its subdirectories, be sure to read the following conventions to understand the file structure and meaning:
[events_spec.md](events_spec.md)

## /items knowledge points

The knowledge-point directory is made of markdown files and a structured directory tree. It records the user's language learning events and knowledge points. Knowledge points that are truly sedimented.

Knowledge-point files are stored in `/items`.

### Definitions

- `knowledge-point directory`: the `/items` directory.
- `knowledge-point`: a specific piece of knowledge when learning a language, such as a vocab word, phrase, grammar, or pragmatics point.
- `knowledge-point entry`: also called `knowledge-point file`. A markdown file that stores one `knowledge-point`.
  - The same `knowledge-point` may have only one `knowledge-point entry`. All content of a `knowledge-point` must be merged into the same `knowledge-point entry`.

- `triggering user message`: the first user message that triggers a particular `knowledge-point` in a conversation.
- `triggering user message envelope`: the message text and the user-action scene contained in the `triggering user message` ([Envelope structured user input format](envelope_spec.md)). It refers to the JSON content wrapped in `<envelope></envelope>` in the `triggering user message`. Much of the information can serve as the scene of a knowledge point, such as the title and URL of the article where a knowledge point appeared.

#### Knowledge types

`knowledge type`, also called `knowledge-point type`, `type`, or `item type`, includes the following categories:

  - `vocab`: vocabulary. Typical content: word, sense, part of speech, etymology, spelling.
  - `phrase`: phrases. Typical content: collocations, idiomatic phrases, fixed collocations.
  - `grammar`: grammar. Typical content: tenses, clauses, sentence patterns, grammar rules.
  - `pragmatics`: pragmatics. Typical content: context, tone, politeness, implied meaning, usage situations.
  - `idiom`: idiom / set phrase. Typical content: break the ice, spill the beans.
  - `culture`: culture. Typical content: English/American culture, slang background, cultural differences.
  - `others`: everything else.

> **Advanced users may edit**: The list above is the authoritative definition of knowledge types in this vault. To add a custom type, append a line in this section and create a subdirectory with the same name under `items/` (auto-created by write), also add a link to the corresponding sub-spec file in [the per-type spec list](#specific-knowledge-point-spec-conventions).
> You may also delete or rename existing types.

### Knowledge-point directory structure

Organized into subdirectories by `knowledge type`. Incomplete example:
```
vocab/ # vocab
  gcc.md
  ambiguous.md
phrase/ # phrases
  take-for-granted.md
grammar/ # grammar
  present.md
pragmatics/ # pragmatics
others/ # others
```

### Basic rules

#### slug basic rules

Used as the human-friendly URL part when generating a wiki static site later. Use a URL-safe English characterset (so translate to English if necessary). But do not use characters that must be escaped or are unsafe in any operating system or URL filename; if present, remove them. Spaces become "-".

#### markdown hyperlinks between `knowledge-point entries`

Hyperlink addresses between `knowledge-point entry` markdown files should use absolute paths. For example:
- correct: [clue](/items/vocab/clue.md)
- wrong: [clue](items/vocab/clue.md)

### Markdown frontmatter fields

Frontmatter fields:

```yaml
ulid: 01JZABD123
type: pragmatics
title: Easily confused when answering Yes or No
description: Easily confused when answering Yes or No
description_in_target_lang: 'Pragmatically, answering "Yes" or "No" can easily lead to confusion.'
created_at: 2026-06-22T18:08:00+08:00
timestamp: 2026-06-26T09:15:00+08:00
schema_version: 1
everlingo_version: 0.1.1-rc.7
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
tags:
  - pragmatics
first_source_kind: web
first_source_url: "https://blog.mygraphql.com/en/posts/ai/ai-life-automatic/ai-job-subcribe/"
first_source_title: "AI-Based Job Position Watching from Company Career Pages(PoC) - Part 1"
```

Field reference:

- ulid: same as the `ulid` in the file-naming format. Guarantees stable uniqueness.
- title: the title of the `knowledge-point entry` note, following these conventions. Written in the `interface language`, must be explicit and concise, limited to one sentence, describing the knowledge point of this file. Used for semantic search and full text search. OKF `title` standard slot.
- description: written in the `interface language`, limited to at most two sentences, describing the knowledge point of this file. Used for semantic search and full text. OKF `description` standard position, a one-sentence summary.
- description_in_target_lang: written in the `target language`, limited to one sentence, describing the knowledge point of this file. Vault extended key (no OKF counterpart). Used for full-text search.
- created_at: creation time, ISO 8601.
- timestamp: update time, using ISO 8601. OKF `timestamp` standard slot.
- schema_version: int. The current frontmatter schema version.
- everlingo_version: the version of EverLingo that created or last updated this file.
- type: `knowledge type`.
- tags: the tags of the `knowledge-point entry`. Supports multiple tags, see below:
  - format: tag names are allowed to contain spaces, but in general avoid spaces or other whitespace. Usually one word.
  - `preset tag`. The `type` field above must also be recorded as a tag in the tags list.
  - smart generation: unless the user explicitly asks, do not generate tags other than the `preset tag` above when generating or modifying `knowledge-point entry`.
- first_source_kind: corresponds to the `source.kind` field in the `triggering user message envelope`.
- first_source_url: corresponds to the `source.url` field in the `triggering user message envelope`.
- first_source_title: corresponds to the `source.title` field in the `triggering user message envelope`.

Auto-generated notes fill as many of the above fields as possible. Hand-written notes minimally should include the following fields:
- type
- title

### File naming

The file-naming format:

```text
{file_main_name}.md
```

In general, if the specific `knowledge type` has no defined value for `file_main_name`, the default is the `title` markdown frontmatter converted via slugification.

For example:

```text
ambiguous.md
aimai.md
te-form.md
```

Note:

- `file_main_name` is the main part of the filename, convenient for humans to browse, and also serves as the human-friendly URL part when generating a wiki static site later. Slug rules are described in the section "Slug basic rules".
- Same-name conflict handling: before creating a new entry, check whether a file with the same name already exists via `ls` / `search`. If an entry for the same knowledge point already exists, reuse (merge content) the existing file; if it is truly a different knowledge point but the slugs happen to be identical, adjust the slug slightly (e.g., append a distinguishing word) before creating.

Avoid the following internal reserved file names:
- `.index.md`

If you need a file with a similar name, append a suffix, such as `index_.md`.

### Common markdown file sections of a knowledge point

#### Encounter history

Encounter history. Record the conversation_context and the source scene of the knowledge point each time it is remembered. This section is placed at the end of the file. **Each time this file is read or written, a line of visit record must be added.**

Example:
```markdown
## Encounter history

- 2026-06-21 12:01:02: While reading the article [UFO event](https://ufo.com/event.html), the user selected the word "will not" to look up its English translation, learned the use of will not / won't to express negative expectation, and asked to record this knowledge point.
- 2026-06-22 13:41:18: On WeChat, the user asked about the difference between "曖昧" and the Chinese word "暧昧".
- 2026-06-26 18:42:48: Ran into it again while reading a Japanese article.
```

**Record links where a knowledge point appears**:

When the following fields have values in the `triggering user message envelope` of the current `knowledge point`:
 - `source.url`
 - `source.title`
the corresponding `encounter record` must include the link where the knowledge point appeared. See the `2026-06-21 12:01:02` record in the example above.

### Specific knowledge-point spec conventions

Each `knowledge type`'s `knowledge-point file` conventions are described, besides the general `knowledge-point file` conventions above, are also in the type-specific conventions. Before reading/writing a specific `knowledge-type` file, be sure to read the relevant `knowledge-type` `knowledge-point file` spec to understand the file structure and meaning:

- [vocab](kb_items_spec_vocab.md)
- [phrase](kb_items_spec_phrase.md)
- [grammar](kb_items_spec_grammar.md)
- [pragmatics](kb_items_spec_pragmatics.md)
- [others](kb_items_spec_others.md)