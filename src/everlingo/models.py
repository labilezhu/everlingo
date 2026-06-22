from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoggingSetting(BaseModel):
    # 日志文件路径，默认: ~/.everlingo/logs/everlingo.log，ref: configuration.md LoggingSetting
    log_file: str = Field(
        default="",
        description="日志文件路径，默认: ~/.everlingo/logs/everlingo.log",
        examples=["/home/user/.everlingo/logs/everlingo.log"],
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
    # 界面语言，可选值: zh-CN, en, ja, fr, de，ref: DOMAIN.md UserProfile
    interface_language: str = Field(
        default="",
        description="界面语言，可选值: zh-CN, en, ja, fr, de",
        examples=["zh-CN"],
    )
    # 目标学习语言，可选值: zh-CN, en, ja, fr, de
    target_language: str = Field(
        default="",
        description="目标学习语言，可选值: zh-CN, en, ja, fr, de，不能与 interface_language 相同",
        examples=["en"],
    )


class UserBackground(BaseModel):
    # 爱好描述
    hobbies: str = Field(
        default="",
        description="爱好描述",
        examples=["历史与文艺"],
    )
    # 主要居住地区
    residence: str = Field(
        default="",
        description="主要居住地区",
        examples=["北京"],
    )
    # 性别，可选值: male, female, other
    gender: str = Field(
        default="",
        description="性别，可选值: male, female, other",
        examples=["male"],
    )


class UserProfile(BaseModel):
    # 语言设置，ref: DOMAIN.md UserProfile
    language: UserLanguage = Field(
        default_factory=UserLanguage,
        description="用户语言设置",
    )
    # 用户背景（可选）
    background: UserBackground = Field(
        default_factory=UserBackground,
        description="用户背景信息",
    )
    # 词典解释风格
    dictionary_definition_style: str = Field(
        default="",
        description="词典解释风格，自定义词典老师返回单词解释时包含的内容",
        examples=["- 词意\n- 词源解释和历史"],
    )

    def is_complete(self) -> bool:
        return bool(self.language.interface_language) and bool(self.language.target_language)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.language.interface_language:
            errors.append("界面语言未设置")
        if not self.language.target_language:
            errors.append("目标学习语言未设置")
        if (
            self.language.interface_language
            and self.language.target_language
            and self.language.interface_language == self.language.target_language
        ):
            errors.append("界面语言和目标学习语言不能相同")
        return errors


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
    "en": "英语",
    "ja": "日本語",
    "zh-CN": "简体中文",
    "fr": "法语",
    "de": "德语",
}
