import functools
import logging

logger = logging.getLogger("everlingo")


def log_tool_call(tool_name: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            arg_parts = []
            for i, a in enumerate(args):
                arg_parts.append(f"arg{i}={a}")
            for k, v in kwargs.items():
                arg_parts.append(f"{k}={v}")
            params = ", ".join(arg_parts)
            logger.debug("tool_name: %s , parameters: %s", tool_name, params)
            result = func(*args, **kwargs)
            logger.debug("tool_name: %s , return: %s", tool_name, result)
            return result

        return wrapper

    return decorator
