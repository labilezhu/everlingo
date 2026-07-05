# Memory Spec

由 markdown 文件、结构化目录组成的 memory 目录 。 保存于 [workspace](/docs/impl-spec/worksplace/workspace.md) 下的 memory 目录。

```bash
    USER.md
    languages/
      en/ # 目标学习语言
         index/
            memory.sqlite # SQLite 索引库
         vault/ # Language Memory Vault

      ja/ # 目标学习语言  
```

Memory Vault 位于 `$workspace/memory/languages/$lang/vault/` 目录下。其中 `$workspace` 是 EverLingo 的 workspace 工作目录，`$lang` 是目标学习语言编码（en / ja / ...）。每个语言独立一个 vault 目录与一个独立的 SQLite 索引库（见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)）。


## Language Memory Vault Spec

每个目标学习语言独立一个 vault 目录，位于 `$workspace/memory/languages/$lang/vault/` 下（见 [workspace.md](/docs/impl-spec/worksplace/workspace.md)）。每语言独立一个 SQLite 索引库（见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)），实现全文搜索的语言隔离。

语言独立一个 vault 目录说明参考：[单语言 Memory Vault Spec](/src/everlingo/mem/vault/vault_spec.md)

# Agent 记忆分层设计

建议不要把所有记忆都叫 memory，而是分层。

## 1. Profile Memory

稳定用户画像。 具体见 [USER-spec.md](/docs/impl-spec/worksplace/USER-spec.md)

---

## 2. Episodic Memory
[events_spec.md](/src/everlingo/mem/vault/events_spec.md)

---

## 3. Semantic Learning Memory

真正沉淀下来的知识点。

[kb_items_spec.md](/src/everlingo/mem/vault/kb_items_spec.md)

---

## 5. Procedural Memory(暂不实现)

Agent 行为规则。

位置：

```text
agent/memory-policy.md
agent/extraction-rules.md
agent/prompt-snippets.md
```

用途：

- 什么需要记；
- 什么不需要记；
- 如何合并重复词条；
- 如何生成复习卡片；
- 如何更新 `USER.md`。

---



