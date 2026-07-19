# ref: gateway.md — Gateway 进程入口
# ref: docs/impl-spec/memory-extract-agent-spec.md — 异步执行
# ref: docs/impl-spec/memory-writer-agent-spec.md — 异步执行（Writer 单例）
#
# 单例抽离避免 python -m 双重导入：本模块不会被当作 __main__ 执行，
# 因此不论 gateway.py 以何种方式加载，memory_writer 都只初始化一次。

import logging

logger = logging.getLogger(__name__)


# ── Memory Writer Agent 单例（进程级）───────────────────────────────
# ref: memory-writer-agent-spec.md — 进程级单例，独立 daemon Thread + queue.Queue。
# Chat Agent 通过 enqueue(entries) 把构造好的 entries 转交给 Writer；
# Writer 异步消费、写入 memory vault。
#
# 延迟导入避免 gateway -> mem_writer_agent -> llm -> ... -> gateway 循环。


class _MemoryWriterProxy:
    """延迟构造的 Writer 单例代理。

    实际 MemoryWriterAgent 在首次访问时构造并 start()。
    这样既能保留「gateway 模块级实例」的单例语义，
    又能在测试中替换为 mock（patch / 直接赋值）。
    """

    def __init__(self) -> None:
        self._agent: object | None = None
        self._notice_sink: object | None = None

    def set_notice_sink(self, sink: object) -> None:
        self._notice_sink = sink
        if self._agent is not None:
            self._agent._notice_sink = sink

    def _ensure(self):
        if self._agent is None:
            from ..mem.agents.mem_writer_agent import MemoryWriterAgent
            self._agent = MemoryWriterAgent(notice_sink=self._notice_sink)
            self._agent.start()
            logger.info("memory_writer started")
        return self._agent

    def enqueue(self, entries) -> None:
        self._ensure().enqueue(entries)

    def get_agent(self):
        """获取或创建 MemoryWriterAgent 实例。"""
        return self._ensure()


memory_writer: _MemoryWriterProxy = _MemoryWriterProxy()
