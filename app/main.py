"""MAX-бот: существующий цикл polling, сессии и сервисы диагностики."""

import logging
import os
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsing import (
    UserInputError, normalize_text, parse_option, unsupported_direction,
    valid_user_id, validate_description,
)
from app.services.analyzer import extract_skills
from app.services.test_engine import select_test_questions, validate_questions
from app.services.scoring import calculate_score, validate_answers
from app.services.feedback import build_feedback

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "https://platform-api2.max.ru")
BOT_TOKEN = os.getenv("BOT_TOKEN")
HEADERS = {"Authorization": BOT_TOKEN}
log = logging.getLogger(__name__)

# Сохраняем принятую архитектуру: один процесс, последовательный polling, память.
user_sessions = {}
_processed_messages = OrderedDict()
_send_times = OrderedDict()
MAX_CACHED_MESSAGES = 2000
YES = {"да", "начать", "начать тест", "готов", "готова", "yes"}
NO = {"нет", "не сейчас", "позже", "no"}
HELP = (
    "Пришли текст Python/backend-стажировки с требованиями. "
    "После подбора теста напиши «да». В тесте отвечай одной латинской буквой или номером варианта.\n"
    "/start — начало; /help — помощь; /continue — текущий шаг; "
    "/restart — пройти выбранный тест заново; /cancel — отменить; /result — последний результат."
)


def get_updates(marker=None):
    params = {"timeout": 30, "types": "message_created"}
    if marker is not None:
        params["marker"] = marker
    response = requests.get(f"{BASE_URL}/updates", headers=HEADERS, params=params, timeout=40)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("updates"), list):
        raise ValueError("Некорректный ответ сервиса обновлений")
    new_marker = data.get("marker", marker)
    if new_marker is not None and (type(new_marker) is not int or new_marker < 0):
        raise ValueError("Некорректный маркер обновлений")
    return {"updates": data["updates"], "marker": new_marker}


def send_message(user_id, text):
    if not valid_user_id(user_id) or not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("Некорректное исходящее сообщение")
    delay = 0.55 - (time.monotonic() - _send_times.get(user_id, float("-inf")))
    if delay > 0:
        time.sleep(delay)
    _send_times[user_id] = time.monotonic()
    _send_times.move_to_end(user_id)
    if len(_send_times) > MAX_CACHED_MESSAGES:
        _send_times.popitem(last=False)
    response = requests.post(
        f"{BASE_URL}/messages", headers=HEADERS, params={"user_id": user_id},
        json={"text": text}, timeout=10,
    )
    response.raise_for_status()
    return response


def _question_text(session):
    questions = session["test_data"]["questions"]
    index = session["current_question"]
    question = questions[index]
    options = "\n".join(f"{i}. {option['id']}: {option['text']}"
                        for i, option in enumerate(question["options"], 1))
    return f"Вопрос {index + 1}/{len(questions)}\n{question['prompt']}\n\n{options}"


def _validate_session(session):
    if not isinstance(session, dict) or session.get("stage") not in {
        "awaiting_confirmation", "in_progress", "restart_confirmation", "completed"
    }:
        raise ValueError("Некорректное состояние сессии")
    questions = session["test_data"]["questions"]
    validate_questions(questions)
    index = session.get("current_question")
    if type(index) is not int or not 0 <= index <= len(questions):
        raise ValueError("Некорректная позиция в тесте")
    validate_answers(session.get("answers"), questions, complete=False)
    if [a["question_id"] for a in session["answers"]] != [q["id"] for q in questions[:index]]:
        raise ValueError("Нарушен порядок ответов")
    if session["stage"] == "in_progress" and index == len(questions):
        raise ValueError("Нет текущего вопроса")
    if session["stage"] == "awaiting_confirmation" and index != 0:
        raise ValueError("Тест начат без подтверждения")
    if session["stage"] == "completed" and (
        index != len(questions) or not isinstance(session.get("result_text"), str)
    ):
        raise ValueError("Неполный результат")
    if session["stage"] == "restart_confirmation" and session.get("previous_stage") not in {
        "awaiting_confirmation", "in_progress", "completed"
    }:
        raise ValueError("Неизвестен предыдущий этап")


def _current_step(session):
    if session["stage"] == "in_progress":
        return _question_text(session)
    if session["stage"] == "awaiting_confirmation":
        return "Тест подготовлен. Напиши «да», чтобы начать, или «не сейчас»."
    if session["stage"] == "restart_confirmation":
        return "Начать выбранный тест заново и очистить его ответы? Напиши «да» или «нет»."
    return session["result_text"]


def analyze_internship(user_id: int, text: str) -> str:
    if not valid_user_id(user_id):
        raise UserInputError("Не удалось определить пользователя.")
    text = validate_description(text)
    if unsupported_direction(text):
        return "Пока поддерживается Python/backend. Пришли описание стажировки этого направления."
    skills = extract_skills(text)
    if not skills:
        return "Не нашёл поддерживаемых навыков. Пришли описание с требованиями по Python, SQL, Git или HTTP/REST."
    skill_ids = [skill["id"] for skill in skills]
    if "python" not in skill_ids:
        return "Не найдено требование Python. Сейчас поддерживаются только Python/backend-стажировки."
    test_data = select_test_questions(skill_ids)
    if "error" in test_data:
        return "Для найденного набора навыков нет готового теста. Нужны Python и хотя бы одна тема: SQL, Git или HTTP/REST. Проверь полноту описания."
    validate_questions(test_data.get("questions"))
    user_sessions[user_id] = {
        "stage": "awaiting_confirmation", "test_data": test_data, "skills": skills,
        "current_question": 0, "answers": [],
    }
    names = ", ".join(skill["name"] for skill in skills)
    return (
        f"Найдены навыки: {names}.\nТест: {test_data['test_name']}, "
        f"вопросов: {len(test_data['questions'])}.\n"
        "Проверяются только базовые темы, не все требования работодателя.\n"
        "Напиши «да», чтобы начать, или «не сейчас»."
    )


def _process_message(user_id, text):
    text = normalize_text(text)
    command = text.casefold()
    session = user_sessions.get(user_id)
    if command == "/help":
        return HELP
    if command == "/cancel":
        user_sessions.pop(user_id, None)
        return "Текущий тест отменён. Пришли новое описание стажировки." if session else HELP
    # Команды с аргументами и неизвестные команды не становятся описаниями/ответами.
    if text.startswith("/") and command not in {"/start", "/continue", "/restart", "/result"}:
        return "Неизвестная команда или лишние аргументы.\n" + HELP
    if session is not None:
        _validate_session(session)
    if command in {"/start", "/continue"}:
        return _current_step(session) if session else HELP
    if command == "/result":
        if session and session["stage"] == "completed":
            return session["result_text"]
        return "Готового результата пока нет. Продолжи тест командой /continue или пришли описание."
    if command == "/restart":
        if not session:
            return "Пока нет выбранного теста. Пришли описание стажировки."
        if session["stage"] != "restart_confirmation":
            session["previous_stage"] = session["stage"]
            session["stage"] = "restart_confirmation"
        return _current_step(session)
    if session and session["stage"] == "restart_confirmation":
        if command in YES:
            session.update(stage="in_progress", current_question=0, answers=[])
            for key in ("previous_stage", "result_text", "question_shown_at"):
                session.pop(key, None)
            return _question_text(session)
        if command in NO:
            session["stage"] = session.pop("previous_stage")
            return "Перезапуск отменён.\n" + _current_step(session)
        return _current_step(session)
    if session and session["stage"] == "awaiting_confirmation":
        if command in YES:
            session["stage"] = "in_progress"
            return _question_text(session)
        if command in NO:
            return "Хорошо, ответы ещё не начаты. Вернуться: /continue. Другое описание: сначала /cancel."
        return "Сначала подтверди начало теста словом «да». Для другого описания используй /cancel."
    if session and session["stage"] == "in_progress":
        return handle_test_response(user_id, text)
    if session and session["stage"] == "completed" and (
        command in YES | NO or len(text) <= 2
    ):
        return "Тест уже завершён. /result — результат, /restart — повторить, или пришли новое описание."
    return analyze_internship(user_id, text)


def process_user_message(user_id: int, text: str) -> str:
    """На ошибке сохраняет последний согласованный прогресс пользователя."""
    if not valid_user_id(user_id):
        return "Не удалось определить пользователя. Открой личный диалог с ботом."
    previous = deepcopy(user_sessions.get(user_id))
    try:
        return _process_message(user_id, text)
    except UserInputError as error:
        reply = str(error)
    except Exception as error:
        # Не отправляем пользователю и в лог текст запроса, токен или детали исключения.
        log.error("Ошибка обработки сообщения: %s", type(error).__name__)
        reply = "Не удалось обработать сообщение. Прогресс сохранён. Попробуй снова; /continue — текущий шаг, /cancel — отмена."
    if previous is None:
        user_sessions.pop(user_id, None)
    else:
        user_sessions[user_id] = previous
    return reply


def handle_test_response(user_id: int, text: str) -> str:
    session = user_sessions.get(user_id)
    if not session:
        return "Активного теста нет. Пришли описание стажировки."
    _validate_session(session)
    if session["stage"] != "in_progress":
        return _current_step(session)
    questions = session["test_data"]["questions"]
    index = session["current_question"]
    question = questions[index]
    try:
        selected_id = parse_option(text, question["options"])
    except UserInputError as error:
        return f"{error}\nНовое описание: сначала /cancel.\n\n{_question_text(session)}"
    answers = session["answers"] + [{
        "question_id": question["id"], "selected_option_id": selected_id,
        "is_correct": selected_id == question["correct_option_id"],
    }]
    if index + 1 < len(questions):
        session.update(answers=answers, current_question=index + 1)
        session.pop("question_shown_at", None)
        return _question_text(session)
    # Сначала полностью рассчитываем ответ; при сбое последний вопрос остаётся активным.
    result = calculate_score(answers, questions)
    feedback = build_feedback(result["wrong_question_ids"], questions)
    status = "Базовая проверка пройдена" if result["is_ready"] else "Есть темы для повторения"
    scores = "\n".join(f"- {skill}: {score}%" for skill, score in result["skill_scores"].items())
    final = (
        f"Тест завершён!\nРезультат: {result['total_score']} ({result['overall_percent']}%).\n"
        f"По навыкам:\n{scores}\n\n{status}.\nЭто оценка только проверенных тем.\n\n"
        f"{feedback}\n\n/result — показать результат; /restart — повторить; или пришли новое описание."
    )
    session.update(answers=answers, current_question=len(questions), stage="completed", result_text=final)
    return final


def _message_parts(text):
    parts = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4001)
        if split_at < 1:
            split_at = 4000
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def handle_update(update):
    """True: событие обработано/неподдерживаемое; False: доставку нужно повторить."""
    if not isinstance(update, dict) or update.get("update_type") != "message_created":
        return True
    message = update.get("message")
    if not isinstance(message, dict):
        return True
    sender, recipient = message.get("sender"), message.get("recipient")
    if not isinstance(sender, dict) or sender.get("is_bot") is not False:
        return True
    user_id = sender.get("user_id")
    if not valid_user_id(user_id):
        return True
    # Текущий адаптер отправляет в личный диалог; групповые сообщения не перехватываем.
    if not isinstance(recipient, dict) or recipient.get("chat_type") != "dialog":
        return True
    body = message.get("body")
    timestamp = message.get("timestamp")
    bodyless = body is None
    if bodyless:
        # У пересылки без собственного текста тело может отсутствовать по API.
        body = {}
    if not isinstance(body, dict):
        return True
    message_id = body.get("mid")
    if bodyless and type(timestamp) is int and timestamp >= 0:
        event_id = ("bodyless", timestamp)
    elif isinstance(message_id, str) and 1 <= len(message_id) <= 256:
        event_id = ("message", message_id)
    else:
        return True
    key = (user_id, event_id)
    cached = _processed_messages.get(key)
    if cached is None:
        # Не принимаем следующий ответ, пока предыдущий вопрос не доставлен.
        if any(k[0] == user_id and not entry["done"] for k, entry in _processed_messages.items()):
            return False
        session = user_sessions.get(user_id)
        timestamp = message.get("timestamp")
        shown_at = session.get("question_shown_at") if isinstance(session, dict) else None
        text = body.get("text")
        if (isinstance(session, dict) and session.get("stage") == "in_progress"
                and type(timestamp) is int and type(shown_at) is int and timestamp < shown_at
                and not (isinstance(text, str) and text.strip().startswith("/"))):
            reply = "Сообщение отправлено до текущего вопроса и не засчитано. Посмотри вопрос через /continue и ответь снова."
        else:
            reply = process_user_message(user_id, text)
        cached = {"parts": _message_parts(reply), "next_part": 0, "done": False}
        _processed_messages[key] = cached
    if cached["done"]:
        return True
    try:
        while cached["next_part"] < len(cached["parts"]):
            part = cached["parts"][cached["next_part"]]
            response = send_message(user_id, part)
            cached["next_part"] += 1
            # Серверная метка времени помогает отсеять ответы, присланные до вопроса.
            session = user_sessions.get(user_id)
            if isinstance(session, dict) and session.get("stage") == "in_progress" and _question_text(session) in part:
                try:
                    sent = response.json().get("message", {})
                    if isinstance(sent, dict) and type(sent.get("timestamp")) is int:
                        session["question_shown_at"] = sent["timestamp"]
                except (ValueError, AttributeError, TypeError):
                    pass
        cached["done"] = True
    except requests.RequestException as error:
        status = error.response.status_code if error.response is not None else None
        if status in {403, 404}:
            # Недоступный диалог не должен останавливать polling для остальных.
            cached["done"] = True
            log.warning("Диалог недоступен, ответ пропущен: HTTP %s", status)
        else:
            log.warning("Не удалось доставить ответ; повторная обработка ввода не требуется")
            return False
    # Ограничиваем память, но не удаляем ещё не доставленные ответы.
    for old_key in list(_processed_messages):
        if len(_processed_messages) <= MAX_CACHED_MESSAGES:
            break
        if _processed_messages[old_key]["done"]:
            del _processed_messages[old_key]
    return True


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден в .env")
    logging.basicConfig(level=logging.INFO)
    log.info("MAX-бот запущен")
    marker = None
    pending = None
    while True:
        try:
            if pending is None:
                pending = get_updates(marker)
            delivered = True
            remaining = []
            for update in pending["updates"]:
                try:
                    if not handle_update(update):
                        delivered = False
                        remaining.append(update)
                except Exception as error:
                    log.error("Ошибка события: %s", type(error).__name__)
                    delivered = False
                    remaining.append(update)
            if delivered:
                marker = pending["marker"]
                pending = None
            else:
                # Повторяем полученные события локально: marker=None при новом
                # запросе может означать только последние обновления на сервере.
                pending["updates"] = remaining
                time.sleep(5)
        except (requests.RequestException, ValueError) as error:
            log.warning("Ошибка получения обновлений: %s", type(error).__name__)
            time.sleep(5)


if __name__ == "__main__":
    main()
