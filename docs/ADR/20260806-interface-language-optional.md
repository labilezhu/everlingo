# ADR: interface_language 改为可选 + OS locale 推断

- 状态：Accepted
- 日期：2026-08-06
- 决策参与方：用户、opencode
- 相关文档：
  - [i18n 整体设计](../i18n/i18n.md)
  - [领域模型](../../DOMAIN.md)
  - [配置参考](../../user-docs/reference/configuration.md)
  - [ADR 20260801-user-onboarding.md](20260801-user-onboarding.md) §9
  - [Chat Agent Spec](../impl-spec/chat-agent-spec.md)

---

## 1. 动机

`interface_language`（界面语言）此前为**必选**配置项：`everlingo.yaml` 中 `user_profile.language.interface_language` 必须非空，且 `UserProfile.validate()` 会因「界面语言未设置」报错，`UserProfile.is_complete()` 会因它为空而返回 False。

这与即将推进的界面国际化（i18n）工作冲突：

1. **首次启动体验**：新用户在尚未完成 onboarding 前，`interface_language` 为空，进程不应因此报错或阻塞；应有一个合理的运行时兜底值使进程可启动、UI 可用。
2. **容器/模板部署**：ws_container 等部署模板原先硬编码 `interface_language: zh-CN`，对非中文用户不友好；希望模板留空，由 OS locale 自动推断。
3. **可用界面语言与可用目标学习语言是两个独立集合**：当前界面语言仅支持 `zh-CN`/`en` 两种，而目标学习语言支持 `en/ja/zh-CN/fr/de` 五种。原先 DOMAIN.md 把两者混在「可用界面语言 包括 en/ja/zh-CN/fr/de」一句中，语义不清。
4. **未来扩展**：onboarding step 1（让用户选界面语言）与 Me 页切换 UI 将在 Phase 3 引入（见 [ADR 20260801](20260801-user-onboarding.md) §9 已为此时机留口）；在此之前需要一个不依赖 UI 的运行时推断机制。

## 2. 关联的规则变更

本 ADR 决定以下领域规则变更：

> **`interface_language` 从「必选」改为「可选」。留空时运行时按 OS locale 推断，兜底 `en`。非空时必须在「可用界面语言」集合内。**

> **「可用界面语言」与「可用目标学习语言」是两个独立集合。当前可用界面语言：`zh-CN`、`en`。界面语言的显示名复用 `LANGUAGES` 字典（单一真源），不为界面语言另建映射表。**

> **`UserProfile.is_complete()` 仅反映 `target_language` 就绪，不再要求 `interface_language` 非空。**

前置/同步变更清单：

| 文件 | 变更 |
|---|---|
| `src/everlingo/models.py` | 新增 `AVAILABLE_INTERFACE_LANGUAGES` 常量 + `resolve_interface_language()` 函数；`UserLanguage.interface_language` description 改可选；`UserProfile.validate()` 删「未设置」+ 新增「非法值」校验；`UserProfile.is_complete()` 去掉 interface 检查 |
| `src/everlingo/setting.py` | 新增 `load_resolved_profile()`（推断值不写回 yaml） |
| `src/everlingo/agents/agent.py` | `_refresh_agent_if_needed()` 中 `load_profile()` → `load_resolved_profile()` |
| `src/everlingo/gateway/gateway.py` | `load_profile()` → `load_resolved_profile()` |
| `DOMAIN.md` | §语言「可用界面语言」改为「当前：zh-CN、en（未来扩展）」+ 强调 interface/target 独立集合、display 名查 `LANGUAGES`；UserProfile 表 interface_language 约束改可选；删「均必须设置」中 interface 部分 |
| `user-docs/reference/configuration.md` | 同步措辞 |
| `everlingo.example.yaml` | interface_language 注释改可选 + 推断说明；示例值改空 |
| `deploy/ws-container/ws-container-spec.md` | 移除/注释默认 `interface_language: zh-CN` |
| `deploy/ws-container/root/home/everlingo/.everlingo/workspaces/default/everlingo.yaml` | 同上 |
| `docs/impl-spec/multiple-users/ws_container_everlingo_template.yaml` | 同上 |
| `deploy/examples/ws_container_everlingo_template.yaml` | 同上 |
| `README.md` | 同上 |
| `user-docs/deployment/simple-single-deployment.md` | 同上 |
| `tests/test_setting.py` | 扩展用例覆盖推断路径、非法值容错、is_complete 语义、resolved 不污染 yaml |

## 3. 概念定义

- **可用界面语言（`AVAILABLE_INTERFACE_LANGUAGES`）**：当前为 `("zh-CN", "en")`，tuple 保序以便 UI 直接 iterate 展示。界面语言的显示名复用 `src/everlingo/models.py` 的 `LANGUAGES[code]`（如 `LANGUAGES["zh-CN"] = "简体中文"`），不为界面语言另建映射表。
- **可用目标学习语言**：`LANGUAGES` 字典的 keys（`en/ja/zh-CN/fr/de`），与可用界面语言是**独立集合**，语义不同，不可混用。
- **`interface_language` 推断（`resolve_interface_language`）**：按下述顺序解析出运行时生效值：
  1. yaml 值非空且 ∈ `AVAILABLE_INTERFACE_LANGUAGES` → 直接用；
  2. `locale.getlocale()` 取 OS 语言，归一化（`lower`、`_`→`-`、去编码后缀）后精确命中可用集 → 返回；
  3. 前缀兜底：`zh*` → `zh-CN`，`en*` → `en`；
  4. 仍未命中 → `"en"`。

## 4. 双访问器（推断值不写回 yaml）

**关键约束**：推断值是运行时兜底，**不写回 yaml**。显式值由 onboarding（Phase 3）或 Me 页切换 UI（Phase 3）写入。

为避免「load → 改字段 → save」路径把推断值静默持久化，采用**双访问器**：

| 访问器 | 返回值语义 | 使用方 |
|---|---|---|
| `load_profile()`（已有，不动） | raw：`interface_language` 可能为空或非法 | `save_profile` / onboarding status / `validate` / `conf_manager` / `user_doc_set` 等所有「读改写」路径 |
| `load_resolved_profile()`（新增） | raw 的副本，`interface_language` 经 `resolve_interface_language()` 填充为非空合法值 | **运行时消费者**：`agent.py` `_refresh_agent_if_needed()`、`gateway.py` 启动横幅 |

这样 save 路径永远走 raw，零泄漏；运行时永远拿到非空合法值。

`load_resolved_profile()` 实现：

```python
def load_resolved_profile() -> UserProfile:
    p = load_profile()
    resolved = resolve_interface_language(p.language.interface_language)
    if resolved != p.language.interface_language:
        p = p.model_copy(update={
            "language": p.language.model_copy(update={"interface_language": resolved})
        })
    return p
```

## 5. `validate()` 与 `load_resolved_profile()` 对非法值的职责分离

| 场景 | `UserProfile.validate()` | `load_resolved_profile()` |
|---|---|---|
| `interface_language` 空 | 不报错（可选） | 走推断 |
| `interface_language` 合法（∈ 可用集） | 不报错 | 直接用 |
| `interface_language` 非法（如 `"fr"`，∉ 可用集） | **报错**「界面语言取值不被支持」 | **走推断容错**（保证进程可启动） |

二者职责分离：`validate()` 供 onboarding/Me 页等 UI 校验场景显式提示用户；`load_resolved_profile()` 保证运行时消费者永远拿到合法值，不因配置错误而崩溃。

## 6. `is_complete()` 语义

`UserProfile.is_complete()` 去掉 `interface_language` 检查，仅 `target_language` 非空即返回 True。

这与 onboarding status 端点（`GET /api/user-profile/status`，见 [ADR 20260801](20260801-user-onboarding.md) §5.1）的 `needs_setup = !is_valid` 语义一致 —— 该端点原本就只看 `target_language` 是否「有效且已初始化」，不检查 `interface_language`。Phase 1 不动该端点。

## 7. 运行时消费者改动点

仅 2 处需改为 `load_resolved_profile()`：

| 文件:行 | 现状 | 改为 |
|---|---|---|
| `src/everlingo/agents/agent.py` `_refresh_agent_if_needed()` 中 `profile = load_profile()` | raw | `load_resolved_profile()` |
| `src/everlingo/gateway/gateway.py` 启动横幅 `profile = load_profile()` | raw | `load_resolved_profile()` |

这两处的下游（`_build_system_prompt(profile, ...)`、`MemoryEntry(interface_language=profile.language.interface_language, ...)`、gateway 启动横幅显示界面语言名）自动拿到非空合法值。

其它所有 `load_profile()` / `load_setting()` 调用点（`user_profile_api.py`、`vault_editor_api.py`、`conf_manager.py`、`tracing.py`、`config.py`、`log_utils.py` 等）**不动** —— 它们要么是「读改写」路径需走 raw，要么不读 `interface_language` 字段。

## 8. 文档与模板同步

见 §2 变更清单。要点：

- `DOMAIN.md` §语言明确「可用界面语言」当前集合与「可用目标学习语言」是独立集合；UserProfile 表 interface_language 约束改可选。
- `everlingo.example.yaml` 与所有部署模板/文档移除硬编码 `interface_language: zh-CN`，改为空 + 注释说明推断行为。
- 容器/裸 yaml 启动时由 OS locale 推断；容器内 `locale.getlocale()` 通常返回 `(None, None)`，会兜底 `en`，这是预期行为（未来 Phase 3 onboarding step 1 会让用户显式选）。

## 9. 与 ADR 20260801 的衔接

[ADR 20260801-user-onboarding.md](20260801-user-onboarding.md) §9 明确：

> **`interface_language` 的可视化设置**：本 ADR 不引入界面语言设置入口。`interface_language` 仍由 yaml / 部署模板配置。未来如需，再另起 ADR。

本 ADR 解决的是「yaml 留空时的运行时兜底」，**不引入**可视化设置入口。可视化设置（onboarding step 1 + Me 页切换 UI）仍留待 Phase 3，届时将另起 ADR 解除 20260801 §9 的「不引入」决定。

Phase 路线图见 [i18n.md](../i18n/i18n.md)。

## 10. 不在本 ADR 范围

- **onboarding step 1（界面语言选择页）**：Phase 3。
- **Me 页界面语言切换 UI**：Phase 3。
- **`/api/user-profile/status` 暴露 `interface_language`**：Phase 3。
- **Web 前端 i18n 框架（react-i18next 等）**：Phase 3。
- **Chat Agent 兜底文案 i18n**：Phase 2（单独一期）。
- **Chrome Extension i18n**：Phase 4。
- **system prompt 本身 i18n**：不做。`_build_system_prompt()` 的中文指令是给 LLM 看的，LLM 会根据 prompt 里的 `interface_lang` 字段自行决定回复语言。

## 11. 实施顺序

1. 源码：`models.py`（常量 + 函数 + validate/is_complete）→ `setting.py`（`load_resolved_profile`）→ `agent.py` / `gateway.py`（2 处调用点）。
2. 测试：`tests/test_setting.py` 扩展，`uv run pytest tests/test_setting.py -v` 通过。
3. 文档与模板：`DOMAIN.md` / `configuration.md` / `everlingo.example.yaml` / 6 处部署模板与文档。
4. ADR：本文件。
5. `TASKS.md` 记录完成项。
