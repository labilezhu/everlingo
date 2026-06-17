from datetime import datetime, timezone, timedelta

from langchain_core.tools import tool

from . import log_tool_call


@tool("clock_get_datetime")
@log_tool_call("clock_get_datetime")
def get_datetime() -> str:
    """返回当前的系统时间"""
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S")
