from typing import Any


def is_valid_resource_config(config: Any) -> bool:
    return type(config.get('name')) is str and type(config.get('scopes')) is list
