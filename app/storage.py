import os
import time
import logging

from dotenv import load_dotenv

from app import handlers, storage

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://platform-api.max.ru")
BOT_TOKEN = os.getenv("BOT_TOKEN")
POLL_INTERVAL = 1  # секунда между запросами, если сервер не поддерживает long polling с таймаутом

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан — проверь .env")

    log.info("Бот запускается. BASE_URL=%s", BASE_URL)
    storage.init()

    # TODO (задача 5.4): сверить с dev.max.ru/docs-api —
    # точное имя метода получения обновлений (GetUpdates / аналог),
    # формат ответа и параметры (offset, timeout и т.п.)
    marker = None
    while True:
        try:
            updates, marker = handlers.fetch_updates(
                base_url=BASE_URL, token=BOT_TOKEN, marker=marker
            )
            for update in updates:
                handlers.handle_update(
                    update, base_url=BASE_URL, token=BOT_TOKEN
                )
        except Exception:
            log.exception("Ошибка в цикле получения обновлений")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
