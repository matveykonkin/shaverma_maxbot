"""
Подсчёт результата по навыкам и применение правил итоговой оценки.
Наполняется в задаче 7 (7.5-7.7).
"""

import os
import time

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://platform-api2.max.ru")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

HEADERS = {
    "Authorization": BOT_TOKEN,
}


def get_updates(marker=None):
    params = {
        "timeout": 30,
        "types": "message_created",
    }

    if marker is not None:
        params["marker"] = marker

    response = requests.get(
        f"{BASE_URL}/updates",
        headers=HEADERS,
        params=params,
        timeout=40,
    )

    response.raise_for_status()
    return response.json()


def send_message(user_id, text):
    response = requests.post(
        f"{BASE_URL}/messages",
        headers=HEADERS,
        params={"user_id": user_id},
        json={"text": text},
        timeout=10,
    )

    response.raise_for_status()


def main():
    print("MAX-бот запущен!")

    marker = None

    while True:
        try:
            data = get_updates(marker)

            marker = data.get("marker")

            for update in data.get("updates", []):
                if update.get("update_type") != "message_created":
                    continue

                message = update.get("message", {})
                sender = message.get("sender", {})

                user_id = sender.get("user_id")

                if user_id is None:
                    continue

                print(f"Получено сообщение от {user_id}")

                send_message(user_id, "Привет! 👋")
                print("Ответ отправлен!")

        except Exception as error:
            print(f"Ошибка: {error}")
            time.sleep(5)


if __name__ == "__main__":
    main()


