# Event Category

Event memory records "when, in which scene and context, you learned what knowledge point."

Purpose:

- Preserve the learning context;
- Support tracing back;
- Support "you asked about this word before";
- Support generating weekly learning reports.

Directory structure:
```
    2026/ #year
      06/ #month
        2026-06-26.md #file name follows this format
    2027/
      08/
        2027-08-26.md
```

## Markdown file example

File preamble:

```markdown
# Events of the Day

Events are recorded in chronological order, i.e., earlier events come first.
Event record format:

```

Each event is appended as a markdown section, e.g.:

Create event (create, default):

```markdown
## Event
- action: created
- chat_session_id: 49c
- entry_id: 6b9
- timestamp: 2026-11-21 14:58:56
- channel_name: WechatChannel
- item_type: vocab
- why_want_to_save_memory: User explicitly asked to save this knowledge point
- lang: ja
- title: 曖昧

### conversation_context
The user looked up a word directly while reading the Japanese novel "Rashōmon"

```

Delete / edit event (delete / edited):

```markdown
## Event
- action: deleted
- timestamp: 2026-11-21 15:00:00
- lang: ja
- title: 曖昧
- item_type: vocab
- file_path: items/vocab/aimai--01JZABD123.md
- chat_session_id: cs-1
- channel_name: WechatChannel

```

`action` values:
- `deleted` — note deleted
- `edited` — note edited

Delete / edit events do **not** include the create event's `why_want_to_save_memory` / `entry_id` / `conversation_context` fields, but add `action` and `file_path` fields instead.