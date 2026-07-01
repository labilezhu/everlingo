# ref: docs/impl-spec/search/memory-vault-search-spec.md — 模块布局
# Memory Vault 全文搜索子包。
# - gateway 进程只 import client.py / protocol.py，不加载 jieba/fugashi/SQLite。
# - indexer 进程加载全部模块，独占 SQLite RW。
