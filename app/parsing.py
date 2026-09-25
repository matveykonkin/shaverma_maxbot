"""Проверки пользовательского ввода без изменения состояния диалога."""

import re
import unicodedata

MIN_DESCRIPTION_LENGTH = 30
MAX_INPUT_LENGTH = 8000
URL_PATTERN = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|www\.|"
    r"(?:[\w-]+\.)+(?:ru|рф|com|org|net|io|dev|me|by|kz)(?=[/:?\s]|$))\S*",
    re.IGNORECASE,
)


class UserInputError(ValueError):
    """Текст ошибки можно показать пользователю без технических подробностей."""


def valid_user_id(value):
    return type(value) is int and 0 < value < 2**63


def normalize_text(value):
    if not isinstance(value, str):
        raise UserInputError(
            "Пришли обычный текст. Фото, файлы, стикеры и голосовые сообщения пока не читаю."
        )
    if len(value) > MAX_INPUT_LENGTH:
        raise UserInputError(f"Сообщение слишком длинное. Оставь не больше {MAX_INPUT_LENGTH} символов.")
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\r\n\t" for c in value):
        raise UserInputError("В тексте есть служебные символы. Скопируй его заново как обычный текст.")
    # Убираем невидимые разделители, BOM и управляющие направлением письма символы.
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    value = unicodedata.normalize("NFKC", value).strip()
    if not value:
        raise UserInputError("Сообщение пустое. Пришли текст описания или ответ на текущий вопрос.")
    if len(value) > MAX_INPUT_LENGTH:
        raise UserInputError(f"Сообщение слишком длинное. Оставь не больше {MAX_INPUT_LENGTH} символов.")
    return value


def without_urls(text):
    return URL_PATTERN.sub(" ", text)


def validate_description(value):
    text = normalize_text(value)
    meaningful = without_urls(text)
    words = re.findall(r"[^\W\d_]+", meaningful, flags=re.UNICODE)
    if URL_PATTERN.search(text) and len(words) < 4:
        raise UserInputError("По ссылке описание не загружаю. Скопируй требования стажировки и пришли текстом.")
    if len(meaningful.strip()) < MIN_DESCRIPTION_LENGTH:
        raise UserInputError("Описание слишком короткое. Пришли хотя бы 30 символов с ролью и требованиями.")
    if len(words) < 4 or sum(len(word) for word in words) < 15:
        raise UserInputError("Не удалось прочитать описание. Нужны роль и требования словами, а не числа или символы.")
    return text


def unsupported_direction(text):
    """Консервативная проверка явно указанной роли, не классификатор профессий."""
    heading = re.split(r"[\n.!?]", without_urls(text).casefold(), maxsplit=1)[0][:250]
    if re.search(r"\b(?:backend|back-end|бэкенд|бекенд)\b", heading):
        return False
    return bool(re.search(
        r"\b(?:frontend|front-end|фронтенд|фронт[еэ]нд|full[ -]?stack|фулстек|"
        r"data\s+(?:scientist|analyst|engineer)|аналитик\w*|"
        r"ml|nlp|mlops|devops|qa|тестировщик\w*|дизайнер\w*|менеджер\w*)\b",
        heading,
    ))


def parse_option(value, options):
    text = normalize_text(value).casefold()
    option_ids = [opt["id"] for opt in options]
    for option_id in option_ids:
        if text == option_id.casefold():
            return option_id
    if re.fullmatch(r"[1-9][0-9]?", text):
        index = int(text) - 1
        if index < len(option_ids):
            return option_ids[index]
    raise UserInputError(
        "Выбери ровно один вариант: латинская буква "
        + ", ".join(option_ids)
        + f" или номер от 1 до {len(option_ids)}. Ответ не засчитан."
    )
