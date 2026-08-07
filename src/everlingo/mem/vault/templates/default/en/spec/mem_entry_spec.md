# Memory Entry Structure

```json
{
  "operation": "create", // "create"(default) | "delete" | "edit"
  "chat_session_id": "", // session id
  "entry_id": "", // newly generated uuid
  "timestamp": "2026-11-21 14:58:56", //yyyymmdd HH:mm:ss
  "channel_name": "WechatChannel", // channel name associated with the session
  "lang": "ja",
  "interface_language": "en",
  "why_want_to_save_memory": "User explicitly asked to save this knowledge point",
  "item_type": "vocab",
  "title": "曖昧",
  "new_messages": "",
  "context_messages": "",
  "file_path": null, // delete/edit required: file path relative to the vault root
  "body": null,      // edit required: new markdown body (without frontmatter)
}
```

## Field reference

- operation: the operation type. `"create"` (default, create/merge entry) / `"delete"` (delete the note file) / `"edit"` (edit the note body). If not provided, defaults to create.
- lang: the target learning language.
- interface_language: the interface language.
- why_want_to_save_memory: why it should be remembered. User explicitly asked to save this knowledge point / Correction item / Chat Agent judgment.
- item_type: the memory type/`knowledge-point type`. Valid values are defined under `knowledge types` in [vault_spec.md](vault_spec.md).
- title: primarily written in the `interface language`, limited to one sentence, describing this `knowledge point`. Used for semantic search and full text search. For delete/edit, the entry's title is only a placeholder.
- new_messages: the conversation messages that triggered the memory. Ignored for delete/edit operations.
- context_messages: the recent history conversation. Ignored for delete/edit operations.
- file_path: required for delete/edit operations. A file path relative to the vault root, e.g., `"items/vocab/aimai--01JZABD123.md"`. Ignored for create operations.
- body: required for edit operations. The new markdown body content (without the frontmatter YAML metadata section). Ignored for delete and create operations.