"""
集成测试：验证统一 Agent 的功能
这些测试需要实际的 LLM API 调用，因此标记为集成测试
"""
import pytest
from everlingo.models import UserProfile
from everlingo.llm import create_llm, create_agent
from everlingo.chat import _build_system_prompt
from everlingo.tools.tools import get_all_tools


@pytest.fixture
def zh_en_profile():
    """中文界面，学习英语的用户配置"""
    return UserProfile(
        interface_language="zh-CN",
        target_language="en",
        hobbies="历史与文艺",
    )


@pytest.fixture
def en_zh_profile():
    """英文界面，学习中文的用户配置"""
    return UserProfile(
        interface_language="en",
        target_language="zh-CN",
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
    zh_en_profile.dictionary_definition_style = """
- 词意
- 词源解释和历史
- 词性
"""
    
    prompt = _build_system_prompt(zh_en_profile)
    
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
