from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LoggingSetting:
    # 日志文件路径，默认: ~/.everlingo/logs/everlingo.log
    log_file: str = ""
    # 日志级别，可选: debug/info/warn/error
    log_level: str = "debug"


@dataclass
class TracingSetting:
    # 跟踪服务，可选: langfuse。空值时不启动 tracing
    tracing_service: str = ""
    # langfuse secret key，如 sk-lf-xxxx
    langfuse_secret_key: str = ""
    # langfuse public key，如 pk-lf-ce-xxxx
    langfuse_public_key: str = ""
    # langfuse base url，如 http://192.168.16.130:3300
    langfuse_base_url: str = ""


@dataclass
class SysSetting:
    # LLM Provider API Key（必需）
    openai_api_key: str = ""
    # 兼容 OpenAI Chat Completions 的 API Base URL
    openai_base_url: str = ""
    # 使用的模型名称
    openai_model: str = ""
    # 日志设定，ref: configuration.md LoggingSetting
    logging_setting: LoggingSetting = field(default_factory=LoggingSetting)
    # 跟踪设定，ref: configuration.md TracingSetting
    tracing_setting: TracingSetting = field(default_factory=TracingSetting)


@dataclass
class UserProfile:
    # 界面语言，可选值: zh-CN, en
    interface_language: str = ""
    # 目标学习语言，可选值: zh-CN, en
    target_language: str = ""
    # 爱好描述
    hobbies: str = ""
    # 主要居住地区
    residence: str = ""
    # 性别，可选值: male, female, other
    gender: str = ""
    # 词典解释风格
    dictionary_definition_style: str = ""

    def is_complete(self) -> bool:
        return bool(self.interface_language) and bool(self.target_language)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.interface_language:
            errors.append("界面语言未设置")
        if not self.target_language:
            errors.append("目标学习语言未设置")
        if self.interface_language and self.target_language and self.interface_language == self.target_language:
            errors.append("界面语言和目标学习语言不能相同")
        return errors


@dataclass
class EverLingoSetting:
    # 系统设定，ref: configuration.md SysSetting
    sys_setting: SysSetting = field(default_factory=SysSetting)
    # 用户 Profile，ref: DOMAIN.md UserProfile
    user_profile: UserProfile = field(default_factory=UserProfile)


@dataclass
class WordQuery:
    word: str
    scene: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    definition: str = ""
    etymology: str = ""
    cultural_context: str = ""
    interface_language: str = ""


@dataclass
class TranslationRecord:
    source_text: str
    target_text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


LANGUAGES: dict[str, str] = {
    "en": "英语",
    "zh-CN": "简体中文",
}
