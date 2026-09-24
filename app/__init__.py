"""
MVP-хранилище состояния диалога.

Задача 5.6: сохранять состояние, выбранный тест, ответы и результат
отдельно для каждого пользователя. Для MVP достаточно словаря в памяти —
переживает перезапуск процесса только если сохранять на диск (см. TODO).
Если нужна устойчивость к перезапуску контейнера (пункт 8.6 плана) —
следующий шаг — заменить на простой файл (json) или sqlite.
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
