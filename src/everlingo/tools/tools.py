from . import conf_manager, clock, user_doc


def get_tools(name: str | None = None) -> list:
    if name == "conf_manager":
        return [conf_manager.get_schema, conf_manager.get_config, conf_manager.set_config]
    if name == "clock":
        return [clock.get_datetime]
    if name == "user_doc":
        return [user_doc.user_doc_get, user_doc.user_doc_set]
    return []


def get_all_tools() -> list:
    return [
        conf_manager.get_schema,
        conf_manager.get_config,
        conf_manager.set_config,
        user_doc.user_doc_get,
        user_doc.user_doc_set,
        clock.get_datetime,
    ]
