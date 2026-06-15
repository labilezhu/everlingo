from . import conf_manager, clock


def get_tools(name: str | None = None) -> list:
    if name == "conf_manager":
        return [conf_manager.get_schema, conf_manager.get_config, conf_manager.set_config]
    if name == "clock":
        return [clock.get_datetime]
    return []


def get_all_tools() -> list:
    return [
        conf_manager.get_schema,
        conf_manager.get_config,
        conf_manager.set_config,
        clock.get_datetime,
    ]
