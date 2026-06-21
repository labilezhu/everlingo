"""
集成测试：验证统一 Agent 的功能
这些测试需要实际的 LLM API 调用，因此标记为集成测试
"""
import pytest
from unittest.mock import MagicMock, patch
from everlingo.models import UserBackground, UserLanguage, UserProfile
from everlingo.llm import create_llm, create_agent
from everlingo.agents.agent import _build_system_prompt, MainAgent, MessageEvent
from langchain_core.messages import HumanMessage, SystemMessage
from everlingo.tools.tools import get_all_tools


@pytest.fixture
def zh_en_profile():
    """中文界面，学习英语的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
        background=UserBackground(hobbies="历史与文艺"),
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
def ja_zh_profile():
    """日本語界面，学习中文的用户配置"""
    return UserProfile(
        language=UserLanguage(interface_language="ja", target_language="zh-CN"),
    )



@pytest.fixture
def agent_zh_en(zh_en_profile):
    """创建中文界面学英语的 Agent"""
    llm = create_llm()
    tools = get_all_tools()
    return create_agent(
        llm,
        tools=tools,
        system_prompt=_build_system_prompt(zh_en_profile)
    )


@pytest.fixture
def agent_en_zh(en_zh_profile):
    """创建英文界面学中文的 Agent"""
    llm = create_llm()
    tools = get_all_tools()
    return create_agent(
        llm,
        tools=tools,
        system_prompt=_build_system_prompt(en_zh_profile)
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
def test_system_prompt_includes_japanese(zh_ja_profile):
    """测试日语配置的 system prompt"""
    prompt = _build_system_prompt(zh_ja_profile)

    assert "日本語" in prompt
    assert "ja" in prompt
    assert "日文词语" in prompt


def test_system_prompt_japanese_interface(ja_zh_profile):
    """测试日本語界面的 system prompt"""
    prompt = _build_system_prompt(ja_zh_profile)

    assert "日本語" in prompt
    assert "ja" in prompt


def test_system_prompt_includes_user_profile(zh_en_profile):
    """测试 system prompt 包含用户配置信息"""
    prompt = _build_system_prompt(zh_en_profile)
    
    # 验证包含必要信息
    assert "界面语言" in prompt
    assert "目标学习语言" in prompt
    assert "简体中文" in prompt
    assert "英语" in prompt
    assert "历史与文艺" in prompt  # 用户爱好
    
    # 验证包含意图识别规则
    assert "查词" in prompt or "Word Lookup" in prompt
    assert "翻译" in prompt or "Translation" in prompt
    assert "配置管理" in prompt


@pytest.mark.integration
def test_custom_dictionary_style(agent_zh_en, zh_en_profile):
    """测试自定义词典风格"""
    custom_profile = zh_en_profile.model_copy(
        update={"dictionary_definition_style": "- 词意\n- 词源解释和历史\n- 词性\n"}
    )
    prompt = _build_system_prompt(custom_profile)
    
    # 验证自定义风格被包含
    assert "词意" in prompt
    assert "词源解释和历史" in prompt
    assert "词性" in prompt


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
    """用 mock 替换 create_llm / create_agent / get_all_tools 创建 MainAgent。"""
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.get_all_tools", return_value=[]), \
         patch("everlingo.agents.agent.create_agent", return_value=mock_inner_agent):
        agent = MainAgent(profile=zh_en_profile)
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
        set_config.invoke({"config_to_be_merged": "user_profile:\n  background:\n    hobbies: 科技"})

    mock_inner2 = MagicMock()
    mock_inner2.invoke.return_value = mock_agent_response

    with patch("everlingo.agents.agent.create_agent", return_value=mock_inner2) as mock_create, \
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile):
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
         patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile):

        # 第一次配置变更 → invoke 触发重建
        set_config.invoke({"config_to_be_merged": "user_profile:\n  background:\n    hobbies: 音乐"})
        agent.invoke(MessageEvent(text="first"))

        # 第二次配置变更 → invoke 再次触发重建
        set_config.invoke({"config_to_be_merged": "user_profile:\n  background:\n    hobbies: 历史"})
        agent.invoke(MessageEvent(text="second"))

    assert len(rebuilt_agents) == 2


# ── 用户显式模式切换单元测试（无需 LLM）─────────────────────────────────

@pytest.fixture
def mock_agent_with_response():
    """创建一个 mock agent，invoke 返回所有输入消息 + AI 回复。"""
    mock = MagicMock()

    def fake_invoke(kwargs):
        messages = list(kwargs["messages"])
        ai_msg = MagicMock()
        ai_msg.content = "mock reply"
        messages.append(ai_msg)
        return {"messages": messages}

    mock.invoke.side_effect = fake_invoke
    return mock


def test_dict_command_switches_mode(zh_en_profile, mock_agent_with_response):
    """/dict 命令应切换到查词模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    reply = agent.invoke(MessageEvent(text="/dict"))

    assert "查词" in reply.text
    assert agent._intent_mode == "dict"


def test_translate_command_switches_mode(zh_en_profile, mock_agent_with_response):
    """/translate 命令应切换到翻译模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    reply = agent.invoke(MessageEvent(text="/translate"))

    assert "翻译" in reply.text
    assert agent._intent_mode == "translate"


def test_slash_command_resets_mode(zh_en_profile, mock_agent_with_response):
    """/ 命令应重置为自动模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))
    assert agent._intent_mode == "dict"

    reply = agent.invoke(MessageEvent(text="/"))
    assert "自动" in reply.text
    assert agent._intent_mode is None


def test_help_command(zh_en_profile, mock_agent_with_response):
    """/help 应返回命令列表和当前模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    reply = agent.invoke(MessageEvent(text="/help"))

    assert "/dict" in reply.text
    assert "/translate" in reply.text
    assert "自动识别" in reply.text


def test_help_shows_current_mode(zh_en_profile, mock_agent_with_response):
    """/help 应显示当前模式。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))

    reply = agent.invoke(MessageEvent(text="/help"))
    assert "查词" in reply.text


def test_unknown_command(zh_en_profile, mock_agent_with_response):
    """未知命令应提示错误。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    reply = agent.invoke(MessageEvent(text="/unknown"))

    assert "未知命令" in reply.text
    assert "/help" in reply.text


def test_dict_mode_injects_system_message(zh_en_profile, mock_agent_with_response):
    """dict 模式下发消息应注入查词模式 SystemMessage。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))

    agent.invoke(MessageEvent(text="serendipity"))

    messages = mock_agent_with_response.invoke.call_args[0][0]["messages"]

    assert any(
        isinstance(m, SystemMessage) and "查词" in m.content
        for m in messages
    )
    assert any(
        isinstance(m, HumanMessage) and m.content == "serendipity"
        for m in messages
    )


def test_translate_mode_injects_system_message(zh_en_profile, mock_agent_with_response):
    """translate 模式下发消息应注入翻译模式 SystemMessage。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/translate"))

    agent.invoke(MessageEvent(text="hello world"))

    messages = mock_agent_with_response.invoke.call_args[0][0]["messages"]

    assert any(
        isinstance(m, SystemMessage) and "翻译" in m.content
        for m in messages
    )
    assert any(
        isinstance(m, HumanMessage) and m.content == "hello world"
        for m in messages
    )


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


def test_mode_persists_across_messages(zh_en_profile, mock_agent_with_response):
    """模式应在多个消息间持续生效。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))

    agent.invoke(MessageEvent(text="hello"))
    msgs1 = mock_agent_with_response.invoke.call_args[0][0]["messages"]

    agent.invoke(MessageEvent(text="world"))
    msgs2 = mock_agent_with_response.invoke.call_args[0][0]["messages"]

    # 两条消息都应包含模式提示
    assert any(
        isinstance(m, SystemMessage) and "查词" in m.content
        for m in msgs1
    )
    assert any(
        isinstance(m, SystemMessage) and "查词" in m.content
        for m in msgs2
    )


def test_mode_history_contains_no_system_message(zh_en_profile, mock_agent_with_response):
    """mode hint SystemMessage 不应被持久化到 self._messages。"""
    agent = _make_main_agent(zh_en_profile, mock_agent_with_response)
    agent.invoke(MessageEvent(text="/dict"))
    agent.invoke(MessageEvent(text="hello"))

    assert not any(isinstance(m, SystemMessage) for m in agent._messages)
