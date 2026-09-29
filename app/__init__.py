"""
MVP-хранилище состояния диалога.
"""

_state: dict[int, dict] = {}


def init() -> None:
    global _state
    _state = {}


def get_user_state(user_id: int) -> dict:
    return _state.setdefault(user_id, {"stage": "start"})


def set_user_state(user_id: int, **fields) -> None:
    state = get_user_state(user_id)
    state.update(fields)
