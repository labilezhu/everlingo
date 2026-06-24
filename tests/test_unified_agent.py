"""
集成测试：验证统一 Agent 的功能
这些测试需要实际的 LLM API 调用，因此标记为集成测试
"""
import pytest
from unittest.mock import MagicMock, patch
from everlingo.models import UserLanguage, UserProfile
from everlingo.llm import create_llm, create_agent
from everlingo.agents.agent import _build_system_prompt, MainAgent, MessageEvent
from everlingo.gateway.channels.channel import ChannelMetadata
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from everlingo.tools.tools import get_all_tools


@pytest.fixture
def default_channel_metadata():
    """默认 ChannelMetadata（无声音能力）"""
    return ChannelMetadata(name="TestChannel")


@pytest.fixture
def zh_en_profile():
    """中文界面，学习英语的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
    )


@pytest.fixture
def en_zh_profile():
    """英文界面，学习中文的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="en", target_language="zh-CN"),
    )


@pytest.fixture
def zh_ja_profile():
    """中文界面，学习日本語的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="ja"),
    )


@pytest.fixture
def zh_fr_profile():
    """中文界面，学习法语的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="fr"),
    )


@pytest.fixture
def en_de_profile():
    """英文界面，学习德语(Deutsch)的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="en", target_language="de"),
    )


@pytest.fixture
def fr_zh_profile():
    """法语界面，学习中文的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="fr", target_language="zh-CN"),
    )


@pytest.fixture
def de_en_profile():
    """德语界面，学习英语的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="de", target_language="en"),
    )

@pytest.fixture
def ja_zh_profile():
    """日本語界面，学习中文的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="ja", target_language="zh-CN"),
    )



@pytest.fixture
def agent_zh_en(zh_en_profile, default_channel_metadata):
    """创建中文界面学英语的 Agent"""
    llm = create_llm()
    tools = get_all_tools()
    return create_agent(
        llm,
        tools=tools,
        system_prompt=_build_system_prompt(zh_en_profile, "", default_channel_metadata),
    )


@pytest.fixture
def agent_en_zh(en_zh_profile, default_channel_metadata):
    """创建英文界面学中文的 Agent"""
    llm = create_llm()
    tools = get_all_tools()
    return create_agent(
        llm,
        tools=tools,
        system_prompt=_build_system_prompt(en_zh_profile, "", default_channel_metadata),
    )


@pytest.mark.integration
def test_word_lookup_english(agent_zh_en):
    """测试查询英语单词"""
    response = agent_zh_en.invoke({
        "messages": [{"role": "user", "content": "serendipity"}]
    })
    
    content = response["messages"][-1].content
    
    # 验证回复包含词典解释的关键元素
    assert content
    assert len(content) > 50  # 应该是详细的解释
    # 应该包含中文解释
    assert any(ord(c) >= 0x4e00 and ord(c) <= 0x9fff for c in content)


@pytest.mark.integration
def test_translation_english_to_chinese(agent_zh_en):
    """测试翻译英语句子到中文"""
    response = agent_zh_en.invoke({
        "messages": [{"role": "user", "content": "The quick brown fox jumps over the lazy dog"}]
    })
    
    content = response["messages"][-1].content
    
    # 验证包含翻译结果和中文
    assert content
    assert any(ord(c) >= 0x4e00 and ord(c) <= 0x9fff for c in content)


@pytest.mark.integration
def test_word_lookup_chinese(agent_en_zh):
    """测试查询中文词语"""
    response = agent_en_zh.invoke({
        "messages": [{"role": "user", "content": "缘分"}]
    })
    
    content = response["messages"][-1].content
    
    # 验证回复存在且有合理长度
    assert content
    assert len(content) > 50


@pytest.mark.integration
def test_translation_chinese_to_english(agent_en_zh):
    """测试翻译中文句子到英文"""
    response = agent_en_zh.invoke({
        "messages": [{"role": "user", "content": "今天天气很好，我们去公园散步吧"}]
    })
    
    content = response["messages"][-1].content
    
    # 验证包含翻译
    assert content
    assert len(content) > 20


@pytest.mark.integration
def test_config_query(agent_zh_en):
    """测试查询配置"""
    response = agent_zh_en.invoke({
        "messages": [{"role": "user", "content": "我的配置是什么？"}]
    })
    
    content = response["messages"][-1].content
    
    # 应该包含配置信息
    assert content
    # 可能会调用 get_config 工具


@pytest.mark.integration
def test_mixed_language_input(agent_zh_en):
    """测试混合语言输入（应该识别为未知意图）"""
    response = agent_zh_en.invoke({
        "messages": [{"role": "user", "content": "hello 你好 world"}]
    })
    
    content = response["messages"][-1].content
    
    # 应该给出提示或澄清询问
    assert content
    assert len(content) > 0


@pytest.mark.integration
def test_system_prompt_includes_japanese(zh_ja_profile, default_channel_metadata):
    """测试日语配置的 system prompt"""
    prompt = _build_system_prompt(zh_ja_profile, "", default_channel_metadata)

    assert "日本語" in prompt
    assert "ja" in prompt
    assert "single_word" in prompt




def test_system_prompt_includes_french(zh_fr_profile, default_channel_metadata):
    """测试法语配置的 system prompt"""
    prompt = _build_system_prompt(zh_fr_profile, "", default_channel_metadata)

    assert "法语" in prompt
    assert "fr" in prompt


def test_system_prompt_includes_german(en_de_profile, default_channel_metadata):
    """测试德语配置的 system prompt"""
    prompt = _build_system_prompt(en_de_profile, "", default_channel_metadata)

    assert "德语" in prompt
    assert "de" in prompt


def test_system_prompt_french_interface(fr_zh_profile, default_channel_metadata):
    """测试法语界面的 system prompt"""
    prompt = _build_system_prompt(fr_zh_profile, "", default_channel_metadata)

    assert "法语" in prompt
    assert "fr" in prompt


def test_system_prompt_german_interface(de_en_profile, default_channel_metadata):
    """测试德语界面的 system prompt"""
    prompt = _build_system_prompt(de_en_profile, "", default_channel_metadata)

    assert "德语" in prompt
    assert "de" in prompt

def test_system_prompt_japanese_interface(ja_zh_profile, default_channel_metadata):
    """测试日本語界面的 system prompt"""
    prompt = _build_system_prompt(ja_zh_profile, "", default_channel_metadata)

    assert "日本語" in prompt
    assert "ja" in prompt


def test_system_prompt_includes_user_profile(zh_en_profile, default_channel_metadata):
    """测试 system prompt 包含用户配置信息"""
    prompt = _build_system_prompt(zh_en_profile, "", default_channel_metadata)

    # 验证包含必要信息
    assert "界面语言" in prompt
    assert "目标学习语言" in prompt
    assert "简体中文" in prompt
    assert "英语" in prompt

    # 验证包含意图识别规则
    assert "查词" in prompt or "Word Lookup" in prompt
    assert "翻译" in prompt or "Translation" in prompt
    assert "管理基本配置" in prompt


def test_system_prompt_omits_user_doc_section_when_empty(zh_en_profile, default_channel_metadata):
    """USER.md 为空时，system prompt 不应包含 USER.md 内容节。"""
    prompt = _build_system_prompt(zh_en_profile, "", default_channel_metadata)
    assert "## 个性化偏好 (USER.md)" not in prompt


def test_system_prompt_includes_user_doc(zh_en_profile, default_channel_metadata):
    """USER.md 非空时，system prompt 应包含其内容，且标题被降级两级。"""
    user_doc = "# 学习目标\n- 雅思 7.0\n## 查词偏好\n- 词意\n- 词源"
    prompt = _build_system_prompt(zh_en_profile, user_doc, default_channel_metadata)

    assert "## 个性化偏好 (USER.md)" in prompt
    assert "雅思 7.0" in prompt
    assert "词源" in prompt
    # 标题应被降级两级： # → ###, ## → ####
    assert "### 学习目标" in prompt
    assert "#### 查词偏好" in prompt
    # 降级后的内容不应包含原样的一级或二级标题（用行边界避免子串误匹配）
    lines = prompt.splitlines()
    assert not any(line.strip().startswith("# 学习目标") for line in lines)
    assert not any(line.strip().startswith("## 查词偏好") for line in lines)


def test_system_prompt_user_doc_headings_demoted(zh_en_profile, default_channel_metadata):
    """验证所有 markdown 标题层级被正确降级两级，非标题行不变。"""
    user_doc = """# h1
## h2
### h3
#### h4
##### h5
###### h6
plain text
- list item
> blockquote"""
    prompt = _build_system_prompt(zh_en_profile, user_doc, default_channel_metadata)

    assert "### h1" in prompt
    assert "#### h2" in prompt
    assert "##### h3" in prompt
    assert "###### h4" in prompt
    assert "####### h5" in prompt
    assert "######## h6" in prompt
    # 降级后的内容不应包含原始标题行（用行边界避免子串误匹配）
    lines = prompt.splitlines()
    assert not any(line.strip().startswith("# h1") for line in lines)
    assert not any(line.strip().startswith("## h2") for line in lines)
    assert "plain text" in prompt
    assert "- list item" in prompt
    assert "> blockquote" in prompt


def test_system_prompt_user_doc_whitespace_only_omitted(zh_en_profile, default_channel_metadata):
    """USER.md 仅含空白时不应注入内容节。"""
    prompt = _build_system_prompt(zh_en_profile, "   \n\n  ", default_channel_metadata)
    assert "## 个性化偏好 (USER.md)" not in prompt


@pytest.mark.integration
def test_multi_turn_conversation(agent_zh_en):
    """测试多轮会话：第二轮引用第一轮的上下文"""
    # 第一轮：查词
    response1 = agent_zh_en.invoke({
        "messages": [{"role": "user", "content": "cat"}]
    })
    content1 = response1["messages"][-1].content
    assert content1
    messages = response1["messages"]

    # 第二轮：代词指代上一轮查的词
    response2 = agent_zh_en.invoke({
        "messages": list(messages) + [{"role": "user", "content": "它的相关词有哪些？"}]
    })
    content2 = response2["messages"][-1].content
    assert content2

    # 第二轮回复应该提到与 cat 相关的词
    related_words = ["dog", "feline", "pet", "kitten", "animal"]
    assert any(word.lower() in (content2 or "").lower() for word in related_words), \
        f"多轮会话未识别代词指代。第二轮回复: {content2}"


# ── 配置版本驱动的 agent 重建单元测试（无需 LLM）─────────────────────────────

@pytest.fixture
def mock_agent_response():
    """构造一个假的 agent invoke 返回值。"""
    msg = MagicMock()
    msg.content = "mock reply"
    return {"messages": [msg]}


def _make_main_agent(zh_en_profile, mock_inner_agent):
    """用 mock 替换 create_llm / create_agent / build_tools 创建 MainAgent。

    不 patch load_user_doc / prompt_input_mtime：让 __init__ 记录真实值，
    这样后续 invoke 中 _refresh_agent_if_needed 比对时不会因 patch 退出而误触发重建。
    """
    from everlingo.gateway.channels.channel import ChannelMetadata
    mock_channel = MagicMock()
    mock_metadata = ChannelMetadata(name="TestChannel")
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.build_tools", return_value=[]), \
         patch("everlingo.agents.agent.create_agent", return_value=mock_inner_agent):
        agent = MainAgent(profile=zh_en_profile, channel_metadata=mock_metadata, channel=mock_channel)
    return agent


def test_agent_no_rebuild_without_config_change(zh_en_profile, mock_agent_response):
    """无配置变更时，invoke() 不应重建 agent。"""
    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    agent = _make_main_agent(zh_en_profile, mock_inner)

    with patch("everlingo.agents.agent.create_agent") as mock_create:
        agent.invoke(MessageEvent(text="hello"))
        agent.invoke(MessageEvent(text="world"))

    mock_create.assert_not_called()


def test_agent_rebuilds_once_after_config_change(zh_en_profile, mock_agent_response):
    """set_config 被调用后，下次 invoke() 应重建 agent 一次。"""
    import everlingo.tools.conf_manager as conf_manager_module
    from everlingo.models import EverLingoSetting, LoggingSetting, SysSetting
    from everlingo.tools.conf_manager import set_config

    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    agent = _make_main_agent(zh_en_profile, mock_inner)

    # 模拟 set_config 工具调用（递增版本号）
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=zh_en_profile,
    )
    with patch("everlingo.tools.conf_manager.load_setting", return_value=setting), \
         patch("everlingo.tools.conf_manager.save_setting"):
        set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: fr"})

    mock_inner2 = MagicMock()
    mock_inner2.invoke.return_value = mock_agent_response

    with patch("everlingo.agents.agent.create_agent", return_value=mock_inner2) as mock_create, \
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
         patch("everlingo.agents.agent.load_user_doc", return_value=""), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
        agent.invoke(MessageEvent(text="hello"))  # 触发重建
        agent.invoke(MessageEvent(text="world"))  # 版本已同步，不再重建

    # create_agent 只应被调用一次（重建时）
    mock_create.assert_called_once()


def test_agent_rebuilds_on_each_config_change(zh_en_profile, mock_agent_response):
    """每次 set_config 后的首次 invoke() 都应触发一次重建。"""
    import everlingo.tools.conf_manager as conf_manager_module
    from everlingo.models import EverLingoSetting, LoggingSetting, SysSetting
    from everlingo.tools.conf_manager import set_config

    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    agent = _make_main_agent(zh_en_profile, mock_inner)

    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=zh_en_profile,
    )

    rebuilt_agents = []

    def fake_create_agent(*args, **kwargs):
        m = MagicMock()
        m.invoke.return_value = mock_agent_response
        rebuilt_agents.append(m)
        return m

    with patch("everlingo.tools.conf_manager.load_setting", return_value=setting), \
         patch("everlingo.tools.conf_manager.save_setting"), \
         patch("everlingo.agents.agent.create_agent", side_effect=fake_create_agent), \
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
         patch("everlingo.agents.agent.load_user_doc", return_value=""), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):

        # 第一次配置变更 → invoke 触发重建
        set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: fr"})
        agent.invoke(MessageEvent(text="first"))

        # 第二次配置变更 → invoke 再次触发重建
        set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: de"})
        agent.invoke(MessageEvent(text="second"))

    assert len(rebuilt_agents) == 2


# ── 用户显式模式切换单元测试（无需 LLM）─────────────────────────────────

@pytest.fixture
def mock_agent_with_response():
    """创建一个 mock agent，invoke 返回所有输入消息 + AI 回复。"""
    mock = MagicMock()

    def fake_invoke(kwargs):
        messages = list(kwargs["messages"])
        ai_msg = AIMessage(content="mock reply")
        messages.append(ai_msg)
        return {"messages": messages}

    mock.invoke.side_effect = fake_invoke
    return mock


def test_dict_command_switches_mode(zh_en_profile, mock_agent_with_response):
    """/dict 命令应切换到查词模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    replies = agent.invoke(MessageEvent(text="/dict"))

    assert "查词" in replies[0].text
    assert agent._intent_mode == "dict"


def test_translate_command_switches_mode(zh_en_profile, mock_agent_with_response):
    """/translate 命令应切换到翻译模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    replies = agent.invoke(MessageEvent(text="/translate"))

    assert "翻译" in replies[0].text
    assert agent._intent_mode == "translate"


def test_slash_command_resets_mode(zh_en_profile, mock_agent_with_response):
    """/ 命令应重置为自动模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))
    assert agent._intent_mode == "dict"

    replies = agent.invoke(MessageEvent(text="/"))
    assert "自动" in replies[0].text
    assert agent._intent_mode is None


def test_help_command(zh_en_profile, mock_agent_with_response):
    """/help 应返回命令列表和当前模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    replies = agent.invoke(MessageEvent(text="/help"))

    assert "/dict" in replies[0].text
    assert "/translate" in replies[0].text
    assert "自动识别" in replies[0].text


def test_help_shows_current_mode(zh_en_profile, mock_agent_with_response):
    """/help 应显示当前模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))

    replies = agent.invoke(MessageEvent(text="/help"))
    assert "查词" in replies[0].text


def test_unknown_command(zh_en_profile, mock_agent_with_response):
    """未知命令应提示错误。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    replies = agent.invoke(MessageEvent(text="/unknown"))

    assert "未知命令" in replies[0].text
    assert "/help" in replies[0].text


def test_original_text_not_polluted(zh_en_profile, mock_agent_with_response):
    """模式提示不应污染用户原文。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))

    agent.invoke(MessageEvent(text="hello"))

    messages = mock_agent_with_response.invoke.call_args[0][0]["messages"]

    # SystemMessage 和 HumanMessage 应分开，不拼接在原文中
    user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    assert any(m.content == "hello" for m in user_msgs)


def test_mode_commands_not_in_history(zh_en_profile, mock_agent_with_response):
    """模式切换命令不应写入会话历史。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))
    agent.invoke(MessageEvent(text="hello"))
    agent.invoke(MessageEvent(text="/translate"))
    agent.invoke(MessageEvent(text="world"))

    # 历史应只包含实际对话，不含命令
    history_texts = [
        m.content for m in agent._messages
        if isinstance(m, HumanMessage)
    ]
    assert history_texts == ["hello", "world"]


def test_mode_history_contains_no_system_message(zh_en_profile, mock_agent_with_response):
    """mode hint SystemMessage 不应被持久化到 self._messages。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))
    agent.invoke(MessageEvent(text="hello"))

    assert not any(isinstance(m, SystemMessage) for m in agent._messages)


# ── USER.md / mtime 驱动的 agent 重建单元测试 ──────────────────────────

def test_agent_rebuilds_on_user_doc_set(zh_en_profile, mock_agent_response):
    """user_doc_set 被调用后，下次 invoke() 应重建 agent 一次。"""
    from everlingo.setting import get_prompt_version
    from everlingo.tools.user_doc import user_doc_set

    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    agent = _make_main_agent(zh_en_profile, mock_inner)

    rebuilt_agents = []

    def fake_create_agent(*args, **kwargs):
        m = MagicMock()
        m.invoke.return_value = mock_agent_response
        rebuilt_agents.append(m)
        return m

    with patch("everlingo.agents.agent.create_agent", side_effect=fake_create_agent), \
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
         patch("everlingo.agents.agent.load_user_doc", return_value="新偏好"), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
         patch("everlingo.tools.user_doc.save_user_doc"), \
         patch("everlingo.tools.user_doc.setting.USER_DOC_PATH") as mock_path:
        mock_path.exists.return_value = False
        user_doc_set.invoke({"content": "新偏好"})
        agent.invoke(MessageEvent(text="hello"))

    assert len(rebuilt_agents) == 1


def test_agent_rebuilds_on_external_mtime_change(zh_en_profile, mock_agent_response):
    """外部编辑 everlingo.yaml / USER.md 导致 mtime 变化时，invoke() 应重建 agent。"""
    from everlingo.gateway.channels.channel import ChannelMetadata
    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    mock_channel = MagicMock()
    mock_metadata = ChannelMetadata(name="TestChannel")
    # __init__ 时 mtime=0.0
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.build_tools", return_value=[]), \
         patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
         patch("everlingo.agents.agent.load_user_doc", return_value=""), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
        agent = MainAgent(profile=zh_en_profile, channel_metadata=mock_metadata, channel=mock_channel)

    rebuilt_agents = []

    def fake_create_agent(*args, **kwargs):
        m = MagicMock()
        m.invoke.return_value = mock_agent_response
        rebuilt_agents.append(m)
        return m

    # mtime 变化（模拟外部编辑），版本号不变
    with patch("everlingo.agents.agent.create_agent", side_effect=fake_create_agent), \
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
         patch("everlingo.agents.agent.load_user_doc", return_value=""), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=99999.0):
        agent.invoke(MessageEvent(text="hello"))

    assert len(rebuilt_agents) == 1


def test_agent_no_rebuild_when_version_and_mtime_unchanged(zh_en_profile, mock_agent_response):
    """版本号与 mtime 均未变化时，连续 invoke 不应重建 agent。"""
    from everlingo.gateway.channels.channel import ChannelMetadata
    mock_inner = MagicMock()
    mock_inner.invoke.return_value = mock_agent_response
    mock_channel = MagicMock()
    mock_metadata = ChannelMetadata(name="TestChannel")
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.build_tools", return_value=[]), \
         patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
         patch("everlingo.agents.agent.load_user_doc", return_value=""), \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
        agent = MainAgent(profile=zh_en_profile, channel_metadata=mock_metadata, channel=mock_channel)

    with patch("everlingo.agents.agent.create_agent") as mock_create, \
         patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
        agent.invoke(MessageEvent(text="hello"))
        agent.invoke(MessageEvent(text="world"))

    mock_create.assert_not_called()


# ── 多消息回复单元测试 ──────────────────────────────────────────────

@pytest.fixture
def multi_ai_agent_response():
    """构造一个模拟「翻译+朗读」场景的 agent response：
    AIMessage 含正文 + tool_calls，ToolMessage 返回 voice scheduled，
    最终 AIMessage 为空。每个非空 AIMessage.content 应作为一个独立回复。
    """
    from langchain_core.messages import AIMessage, ToolMessage

    def fake_invoke(kwargs):
        input_msgs = list(kwargs["messages"])
        ai_msg = AIMessage(
            content="UFO — 不明飞行物 (Unidentified Flying Object)",
            tool_calls=[{
                "id": "call_1",
                "name": "voice_speak",
                "args": {"text": "UFO"},
            }],
        )
        tool_msg = ToolMessage(content="voice scheduled", tool_call_id="call_1")
        final_ai = AIMessage(content="")
        return {"messages": input_msgs + [ai_msg, tool_msg, final_ai]}

    mock = MagicMock()
    mock.invoke.side_effect = fake_invoke
    return mock


def test_invoke_returns_one_message_per_nonempty_ai_message(
    zh_en_profile, multi_ai_agent_response
):
    """工具循环产生 [AIMessage(翻译), ToolMessage, AIMessage("")] 时，
    invoke 应返回 1 条回复（跳过 ToolMessage，跳过空 AIMessage）。
    """
    agent = _make_main_agent(zh_en_profile, multi_ai_agent_response)
    replies = agent.invoke(MessageEvent(text="翻译并朗读 ufo"))

    assert len(replies) == 1
    assert "UFO" in replies[0].text
    assert "不明飞行物" in replies[0].text


def test_invoke_returns_multiple_messages_when_multiple_ai_have_content(
    zh_en_profile,
):
    """两条 AIMessage 都有非空 content 时，invoke 应返回 2 条回复（多气泡）。"""
    from langchain_core.messages import AIMessage

    mock_inner = MagicMock()

    def fake_invoke(kwargs):
        input_msgs = list(kwargs["messages"])
        return {"messages": input_msgs + [
            AIMessage(content="第一段：UFO 是..."),
            AIMessage(content="第二段：补充说明..."),
        ]}

    mock_inner.invoke.side_effect = fake_invoke
    agent = _make_main_agent(zh_en_profile, mock_inner)

    replies = agent.invoke(MessageEvent(text="介绍 UFO"))

    assert len(replies) == 2
    assert replies[0].text == "第一段：UFO 是..."
    assert replies[1].text == "第二段：补充说明..."


def test_invoke_returns_empty_when_no_ai_content(zh_en_profile):
    """LLM 只调工具无文字时，invoke 返回空列表（语音由工具异步直发）。"""
    from langchain_core.messages import AIMessage, ToolMessage

    mock_inner = MagicMock()

    def fake_invoke(kwargs):
        input_msgs = list(kwargs["messages"])
        return {"messages": input_msgs + [
            AIMessage(content="", tool_calls=[{
                "id": "call_1",
                "name": "voice_speak",
                "args": {"text": "ufo"},
            }]),
            ToolMessage(content="voice scheduled", tool_call_id="call_1"),
            AIMessage(content=""),
        ]}

    mock_inner.invoke.side_effect = fake_invoke
    agent = _make_main_agent(zh_en_profile, mock_inner)

    replies = agent.invoke(MessageEvent(text="朗读 ufo"))
    assert replies == []


def test_invoke_persists_tool_messages_in_history(zh_en_profile, multi_ai_agent_response):
    """self._messages 应保留 ToolMessage（多轮 LLM 上下文需要工具结果）。"""
    agent = _make_main_agent(zh_en_profile, multi_ai_agent_response)
    agent.invoke(MessageEvent(text="翻译并朗读 ufo"))

    tool_msgs = [m for m in agent._messages if m.type == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == "voice scheduled"


def test_invoke_error_returns_single_element_list(zh_en_profile):
    """agent.invoke 抛异常时，invoke 返回单元素列表（含错误信息）。"""
    from langchain_core.messages import AIMessage

    mock_inner = MagicMock()
    mock_inner.invoke.side_effect = RuntimeError("llm down")
    agent = _make_main_agent(zh_en_profile, mock_inner)

    replies = agent.invoke(MessageEvent(text="hello"))
    assert len(replies) == 1
    assert "llm down" in replies[0].text
