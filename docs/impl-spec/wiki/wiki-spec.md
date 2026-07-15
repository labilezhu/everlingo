讨论一下后面的产品设计计划与架构计划。

# Wiki 规范

现在产品经有建立 [Vault](src/everlingo/mem/vault/vault_specs/default/vault_spec.md) 的基本能力。如何把这些 markdown vault 变成见面，让用户可以方便地浏览和访问。

## Wiki 构建

构建 static site 选型： Material for MkDocs 好吗？ 还是 [VitePress](https://vitepress.dev/guide/what-is-vitepress) 还是 [Quartz](https://quartz.jzhao.xyz/)

## Wiki 服务

复用现有的 docs/impl-spec/web-session-acceptor.md 的 web server 吗？ 还是独立进程，我建议是独立进程。