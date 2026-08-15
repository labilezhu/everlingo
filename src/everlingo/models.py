import locale
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoggingSetting(BaseModel):
    # 日志文件路径，默认: $workspace/logs/everlingo.log，ref: configuration.md LoggingSetting
    log_file: str = Field(
        default="",
        description="日志文件路径，默认: $workspace/logs/everlingo.log",
        examples=["$workspace/logs/everlingo.log"],
    )
    # 日志级别，可选: debug/info/warn/error
    log_level: Literal["debug", "info", "warn", "error"] = Field(
        default="debug",
        description="日志级别，可选: debug/info/warn/error",
        examples=["debug"],
    )


class TracingSetting(BaseModel):
    # 跟踪服务，可选: langfuse。空值时不启动 tracing，ref: configuration.md TracingSetting
    tracing_service: str = Field(
        default="",
        description="跟踪服务，可选: langfuse。空值时不启动 tracing",
        examples=["langfuse"],
    )
    # langfuse secret key，如 sk-lf-xxxx
    langfuse_secret_key: str = Field(
        default="",
        description="langfuse secret key",
        examples=["sk-lf-xxxx"],
    )
    # langfuse public key，如 pk-lf-ce-xxxx
    langfuse_public_key: str = Field(
        default="",
        description="langfuse public key",
        examples=["pk-lf-ce-xxxx"],
    )
    # langfuse base url，如 http://192.168.16.130:3300
    langfuse_base_url: str = Field(
        default="",
        description="langfuse base url",
        examples=["http://192.168.16.130:3300"],
    )


class SysSetting(BaseModel):
    # LLM Provider API Key（必需），ref: configuration.md SysSetting
    openai_api_key: str = Field(
        default="",
        description="LLM Provider API Key（必需）",
        examples=["sk-xxxx"],
    )
    # 兼容 OpenAI Chat Completions 的 API Base URL
    openai_base_url: str = Field(
        default="",
        description="兼容 OpenAI Chat Completions 的 API Base URL",
        examples=["https://openrouter.ai/api/v1"],
    )
    # 使用的模型名称
    openai_model: str = Field(
        default="",
        description="使用的模型名称",
        examples=["gpt-4o-mini"],
    )
    # Embedding 模型名称（可选）。空值时表示不启用 embedding 相关功能。
    # 复用 openai_api_key / openai_base_url，指向 OpenRouter 上的 embedding 模型
    # （如 openai/text-embedding-3-small）。无默认值，必须显式配置。
    openai_embedding_model: str = Field(
        default="",
        description="Embedding 模型名称（可选，无默认值）",
        examples=["openai/text-embedding-3-small"],
    )
    # Vision 模型名称（可选）。复用 openai_api_key / openai_base_url。
    # 空值时回退到 env VISION_MODEL，再回退默认 xiaomi/mimo-v2.5。
    # ref: docs/ADR/20260812-image-chat.md §19 — Vision Service
    vision_model: str = Field(
        default="",
        description="Vision 模型名称（可选，无默认值）",
        examples=["xiaomi/mimo-v2.5"],
    )
    # 日志设定，ref: configuration.md LoggingSetting
    logging_setting: LoggingSetting = Field(
        default_factory=LoggingSetting,
        description="日志设定",
    )
    # 跟踪设定，ref: configuration.md TracingSetting
    tracing_setting: TracingSetting = Field(
        default_factory=TracingSetting,
        description="跟踪设定",
    )


class UserLanguage(BaseModel):
    # 界面语言，可选；留空时按 OS locale 推断，兜底 en；非空时必须在可用界面语言内。
    # ref: docs/ADR/20260806-interface-language-optional.md
    interface_language: str = Field(
        default="",
        description="界面语言，可选；留空时按 OS locale 推断，兜底 en；非空时必须在可用界面语言内",
        examples=["zh-CN"],
    )
    # 目标学习语言，可选值: zh-CN, en, ja, fr, de
    target_language: str = Field(
        default="",
        description="目标学习语言，可选值: zh-CN, en, ja, fr, de",
        examples=["en"],
    )


class UserProfile(BaseModel):
    # 语言设置，ref: DOMAIN.md UserProfile
    language: UserLanguage = Field(
        default_factory=UserLanguage,
        description="用户语言设置",
    )

    def is_complete(self) -> bool:
        return bool(self.language.target_language)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.language.interface_language and (
            self.language.interface_language not in AVAILABLE_INTERFACE_LANGUAGES
        ):
            errors.append("界面语言取值不被支持")
        if not self.language.target_language:
            errors.append("目标学习语言未设置")
        return errors


class WebListener(BaseModel):
    interface: str = Field(
        default="localhost",
        description="Web 监听接口，默认 localhost",
        examples=["localhost", "0.0.0.0"],
    )
    port: int = Field(
        default=8000,
        description="Web 监听端口，默认 8000",
        examples=[8000],
    )


class WebPublicAddress(BaseModel):
    base_url: str = Field(
        default="",
        description="浏览器访问地址。空值表示从 listener 生效配置自动生成（http://{interface}:{port}）",
        examples=["http://localhost:8000", "https://everlingo.example.com"],
    )


class ChannelWeb(BaseModel):
    listener: WebListener = Field(default_factory=WebListener, description="监听地址")
    public_address: WebPublicAddress = Field(
        default_factory=WebPublicAddress, description="浏览器访问地址"
    )


class ChannelWechat(BaseModel):
    # 是否启用 wechat channel（重启后自动启动）。节点不存在 = 未启用。
    # ref: workspace-console/ws-console-arch.md §7 自动启动与 enable 持久化
    enable: bool = Field(
        default=False,
        description="是否启用 wechat channel（重启后自动启动）",
        examples=[False, True],
    )


class Channels(BaseModel):
    channel_web: ChannelWeb = Field(
        default_factory=ChannelWeb, description="Web Session Acceptor 配置"
    )
    channel_wechat: ChannelWechat = Field(
        default_factory=ChannelWechat, description="Wechat 通道配置（enable 持久化）"
    )


class Plugins(BaseModel):
    channels: Channels = Field(default_factory=Channels, description="通道插件配置")


class GitBackupAuth(BaseModel):
    # 凭证模式。ssh：git@host 传输；https_pat：HTTPS + PAT Basic Auth；https_none：HTTPS 无认证
    method: Literal["ssh", "https_pat", "https_none"] = Field(
        default="ssh",
        description="凭证模式：ssh / https_pat / https_none",
        examples=["ssh"],
    )
    # ssh 模式私钥路径；空=用系统 ~/.ssh/
    ssh_private_key_file: str = Field(
        default="",
        description="ssh 模式私钥路径；空=系统 ~/.ssh/",
        examples=["/run/secrets/git_backup_ssh_key"],
    )
    # https_pat 模式 PAT（GitHub fine-grained PAT，contents:write）
    pat: str = Field(
        default="",
        description="https_pat 模式 PAT（GitHub fine-grained PAT，contents:write）",
        examples=["github_pat_xxx"],
    )


class GitBackup(BaseModel):
    # 是否启用自动 commit + 自动 push
    enabled: bool = Field(
        default=False,
        description="是否启用自动 commit + 自动 push",
        examples=[False, True],
    )
    # 任意 git remote，如 git@github.com:user/vault.git
    remote_url: str = Field(
        default="",
        description="任意 git remote，如 git@github.com:user/vault.git",
        examples=["git@github.com:user/vault.git"],
    )
    # 上游分支
    branch: str = Field(
        default="main",
        description="上游分支",
        examples=["main"],
    )
    auth: GitBackupAuth = Field(
        default_factory=GitBackupAuth,
        description="远端凭证",
    )
    # 自动 commit 去抖秒（文件变更后多久聚合一次 commit）
    commit_interval: int = Field(
        default=300,
        description="自动 commit 去抖秒",
        examples=[300],
    )
    # 自动 push 间隔秒；0=仅手动触发
    push_interval: int = Field(
        default=300,
        description="自动 push 间隔秒；0=仅手动触发",
        examples=[300, 0],
    )


class EverLingoSetting(BaseModel):
    # 系统设定，ref: configuration.md SysSetting
    sys_setting: SysSetting = Field(
        default_factory=SysSetting,
        description="系统设定",
    )
    # 用户 Profile，ref: DOMAIN.md UserProfile
    user_profile: UserProfile = Field(
        default_factory=UserProfile,
        description="用户 Profile",
    )
    # Memory Vault 版本控制与远端备份，ref: vault-version-control.md
    git_backup: GitBackup = Field(
        default_factory=GitBackup,
        description="Memory Vault 版本控制与远端备份",
    )
    # 插件配置，ref: configuration.md Plugins
    plugins: Plugins = Field(
        default_factory=Plugins,
        description="插件配置",
    )


class WordQuery(BaseModel):
    word: str = Field(description="查询的单词")
    scene: str = Field(default="", description="使用场景")
    timestamp: datetime = Field(default_factory=datetime.now, description="查询时间")
    definition: str = Field(default="", description="词义解释")
    etymology: str = Field(default="", description="词源")
    cultural_context: str = Field(default="", description="文化背景")
    interface_language: str = Field(default="", description="界面语言")


class TranslationRecord(BaseModel):
    source_text: str = Field(description="原文")
    target_text: str = Field(default="", description="译文")
    source_lang: str = Field(default="", description="源语言")
    target_lang: str = Field(default="", description="目标语言")
    timestamp: datetime = Field(default_factory=datetime.now, description="翻译时间")


LANGUAGES: dict[str, str] = {
    "en": "English",
    "ja": "日本語",
    "zh-CN": "简体中文",
    "fr": "Français",
    "de": "Deutsch",
}


# 可用界面语言。当前：zh-CN / en（未来扩展）。
# 显示名复用 LANGUAGES[code]（如 LANGUAGES["zh-CN"] = "简体中文"），不为界面语言另建映射。
# 可用界面语言与可用目标学习语言（LANGUAGES keys）是两个独立集合，语义不同。
# tuple 保序，便于 UI 直接 iterate 展示。
# ref: docs/ADR/20260806-interface-language-optional.md
AVAILABLE_INTERFACE_LANGUAGES: tuple[str, ...] = ("zh-CN", "en")


def _normalize_lang_tag(tag: str) -> str:
    """归一化语言标签：小写、`_`→`-`、去编码后缀（如 `zh_CN.UTF-8` → `zh-cn`）。

    ref: docs/ADR/20260806-interface-language-optional.md §3
    供 resolve_interface_language / i18n.parse_accept_language 复用。
    """
    return tag.lower().split(".")[0].replace("_", "-")


def resolve_interface_language(value: str) -> str:
    """解析运行时生效的界面语言。

    顺序：
    1. value 非空且 ∈ AVAILABLE_INTERFACE_LANGUAGES → 直接用
    2. locale.getlocale() 取 OS 语言，归一化（lower、_→-、去编码后缀）后精确命中可用集 → 返回
    3. 前缀兜底：zh* → zh-CN，en* → en
    4. 兜底 "en"

    推断值只用于运行时，不写回 yaml。
    ref: docs/ADR/20260806-interface-language-optional.md §3
    """
    if value and value in AVAILABLE_INTERFACE_LANGUAGES:
        return value

    lang, _ = locale.getlocale()  # 可能 (None, None)，如容器环境
    if lang:
        normalized = _normalize_lang_tag(lang)
        if normalized in AVAILABLE_INTERFACE_LANGUAGES:
            return normalized
        if normalized.startswith("zh-") or normalized == "zh":
            return "zh-CN"
        if normalized.startswith("en-") or normalized == "en":
            return "en"
    return "en"
