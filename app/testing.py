import logging
import requests

log = logging.getLogger("bot.handlers")


def fetch_updates(base_url: str, token: str, marker=None):
    """
    Запрашивает новые обновления у MAX.

    TODO (задача 5.4): проверить по официальной документации
    (dev.max.ru/docs-api) точный путь метода, формат заголовка
    авторизации и структуру ответа — здесь пока заглушка-каркас.
    """
    headers = {"Authorization": token}
    params = {}
    if marker is not None:
        params["marker"] = marker

    response = requests.get(f"{base_url}/updates", headers=headers, params=params, timeout=35)
    response.raise_for_status()
    data = response.json()

    updates = data.get("updates", [])
    new_marker = data.get("marker", marker)
    return updates, new_marker


def send_message(base_url: str, token: str, chat_id, text: str) -> None:
    """
    Отправляет сообщение пользователю.

    TODO (задача 5.4): свериться с документацией — точный путь метода
    (например POST /messages), формат тела запроса и допустимые поля.
    """
    headers = {"Authorization": token}
    payload = {"chat_id": chat_id, "text": text}

    response = requests.post(f"{base_url}/messages", headers=headers, json=payload, timeout=15)
    response.raise_for_status()


def handle_update(update: dict, base_url: str, token: str) -> None:
    """
    Точка входа для одного входящего события.

    На этапе 5.10 достаточно echo-логики, чтобы подтвердить,
    что бот отвечает. Дальнейшая логика (парсинг описания,
    тестирование, оценка) добавится в задачах 6-7.
    """
    log.info("Получено обновление: %s", update)

    # TODO: разобрать реальную структуру update согласно документации,
    # достать chat_id и текст сообщения
    chat_id = update.get("chat_id")
    text = update.get("text", "")

    if chat_id is None:
        return

    reply = f"Принял: {text}" if text else "Привет! Пришли описание стажировки."
    send_message(base_url, token, chat_id, reply)
