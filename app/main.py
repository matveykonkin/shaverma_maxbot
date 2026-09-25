"""
MAX-бот для проверки готовности к стажировкам.
Использует rule-based анализатор и тест-движок.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.analyzer import extract_skills
from app.services.test_engine import select_test_questions
from app.services.scoring import calculate_score
from app.services.feedback import build_feedback
from app.database import (
    save_test_session, get_test_session, clear_test_session,
    save_user_answer, get_user_answers, save_test_result, 
    get_test_history, get_user_stats
)

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SKILLS_FILE = DATA_DIR / "skills.json"

with open(SKILLS_FILE, "r", encoding="utf-8") as f:
    skills_data = json.load(f)

AVAILABLE_SKILLS = [skill["name"] for skill in skills_data.get("skills", [])]
SKILLS_LIST_TEXT = ", ".join(AVAILABLE_SKILLS[:-1]) + " и " + AVAILABLE_SKILLS[-1] if len(AVAILABLE_SKILLS) > 1 else AVAILABLE_SKILLS[0]

BASE_URL = os.getenv("BASE_URL", "https://platform-api2.max.ru")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

HEADERS = {
    "Authorization": BOT_TOKEN,
}

# Простое хранилище состояния в памяти
user_sessions = {}


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
    return response


def analyze_internship(user_id: int, text: str) -> str:
    """Анализирует описание стажировки и возвращает результат."""
    skills = extract_skills(text)
    
    if not skills:
        return (
            "Не нашёл в описании поддерживаемых навыков (Python, SQL, Git, HTTP). "
            "Пожалуйста, убедитесь, что текст содержит технические требования."
        )
    
    # Формируем ответ о найденных навыках
    skills_text = ", ".join([f"{s['name']}" for s in skills])
    skill_ids = [s["id"] for s in skills]
    
    # Подбираем тест
    test_data = select_test_questions(skill_ids)
    
    if "error" in test_data:
        return f"К сожалению, по навыкам ({skills_text}) нет готового теста."
    
     # Подготавливаем данные для сессии
    session_data = {
        "test_data": test_data,
        "skills": skills,
        "current_question": 0,
        "answers": [],
        "started_at": datetime.now().isoformat()
    }
    
    # Сохраняем сессию в SQLite
    save_test_session(user_id, session_data)
    
    msg = (
        f"В стажировке важны навыки: {skills_text}.\n\n"
        f"Я подготовил короткую проверку: {test_data['test_name']} "
        f"(вопросов: {len(test_data['questions'])}).\n\n"
        "Готов пройти тест?"
    )
    
    return msg


def process_user_message(user_id: int, text: str) -> str:
    """Обрабатывает сообщение пользователя в зависимости от состояния."""
    
    # Обработка команд
    text_lower = text.strip().lower()
    
    if text_lower in ["/stats", "/progress", "статистика"]:
        return get_user_stats_command(user_id)
    elif text_lower in ["/history", "история"]:
        return get_test_history_command(user_id)
    elif text_lower in ["/restart", "перезапуск", "начать заново"]:
        return restart_command(user_id)
    
    # Проверяем, есть ли активная сессия теста
    session = get_test_session(user_id)
    
    if session and "test_data" in session:
        # Пользователь проходит тест
        return handle_test_response(user_id, text, session)
    
    # Если сессии нет - анализируем как описание стажировки
    if len(text) < 15:
        return (
            f"Привет! Пришли описание стажировки. Я выделю ключевые навыки и проверю твои знания по ним коротким тестом.\n\n"
            f"Навыки, по которым доступны тесты: {SKILLS_LIST_TEXT}.\n\n"
            f"Описание должно быть длиннее 15 символов, а также содержать названия конкретных навыков (например, SQL, Python, Git)\n\n"
            f"Пример описания: Требуется Python, знание SQL, работа с Git.")
    
    return analyze_internship(user_id, text)


def handle_test_response(user_id: int, text: str, session: dict) -> str:
    """Обрабатывает ответ на вопрос теста."""
    test_data = session["test_data"]
    questions = test_data["questions"]
    current_idx = session["current_question"]
    
    if current_idx >= len(questions):
        return "Тест уже завершен. Пришли новое описание стажировки."
    
    current_question = questions[current_idx]
    
    # Проверяем, что пользователь выбрал вариант ответа
    try:
        selected_option_id = text.strip().lower()
        # Ищем подходящий вариант
        option = next(
            (opt for opt in current_question["options"] 
             if opt["id"].lower() == selected_option_id),
            None
        )
        
        if not option:
            # Показываем доступные варианты
            options_text = "\n".join([
                f"{opt['id']}: {opt['text']}" 
                for opt in current_question["options"]
            ])
            return f"Выбери вариант:\n{options_text}"
        
        is_correct = option["id"] == current_question["correct_option_id"]
        
        # СОХРЯНЯЕМ ОТВЕТ В SQLite
        answer_data = {
            "question_id": current_question["id"],
            "question_text": current_question["prompt"],
            "selected_option_id": option["id"],
            "selected_option_text": option["text"],
            "is_correct": is_correct,
            "correct_option_id": current_question["correct_option_id"],
            "skill_id": current_question.get("skill_id", "unknown")
        }
        save_user_answer(user_id, current_question["id"], answer_data)
        
        # Обновляем сессию в памяти
        session["answers"].append({
            "question_id": current_question["id"],
            "selected_option_id": option["id"],
            "is_correct": is_correct
        })
        session["current_question"] += 1
        
        # Обновляем сессию в SQLite
        save_test_session(user_id, session)
        
        total_questions = len(questions)
        passed_questions = session["current_question"]
        remaining_questions = total_questions - passed_questions
        progress_text = f"Прогресс: {passed_questions}/{total_questions} (осталось {remaining_questions})"
        
        if session["current_question"] < total_questions:
            next_q = questions[session["current_question"]]
            options_text = "\n".join([
                f"{opt['id']}: {opt['text']}" 
                for opt in next_q["options"]
            ])
            return (
                f"{progress_text}\n\n"
                f"Следующий вопрос:\n{next_q['prompt']}\n\n"
                f"{options_text}"
            )
        else:
            # Завершаем тест
            result = calculate_score(session["answers"], questions)
            
            # СОХРЯНЯЕМ РЕЗУЛЬТАТ ТЕСТА в SQLite
            test_result = {
                "test_id": test_data["test_id"],
                "test_name": test_data["test_name"],
                "total_score": result["total_score"],
                "overall_percent": result["overall_percent"],
                "skill_scores": result["skill_scores"],
                "is_ready": result["is_ready"],
                "questions_count": len(questions)
            }
            save_test_result(user_id, test_result)
            
            # Формируем фидбэк
            feedback = build_feedback(
                wrong_ids=result["wrong_question_ids"],
                questions=questions,
                user_answers=session["answers"]
            )
            
            status = "✅ Готов к отклику" if result["is_ready"] else "⚠️ Нужно подтянуть"
            
            final_msg = (
                f"Тест завершен! 🎉\n\n"
                f"Пройдено: {total_questions}/{total_questions} вопросов.\n\n"
                f"Общий результат: {result['total_score']} ({result['overall_percent']}%)\n\n"
                f"По навыкам:\n" + 
                "\n".join([
                    f"- {skill}: {score}%" 
                    for skill, score in result["skill_scores"].items()
                ]) +
                f"\n\n{status}\n\n{feedback}"
            )
            
            # Удаляем активную сессию
            clear_test_session(user_id)
            return final_msg
            
    except Exception as e:
        return f"Ошибка при обработке ответа: {e}"

def get_user_stats_command(user_id: int) -> str:
    """Команда для просмотра статистики."""
    stats = get_user_stats(user_id)
    
    if stats["total_tests"] == 0:
        return "У вас пока нет пройденных тестов. Начните с отправки описания стажировки!"
    
    msg = "📊 Ваша статистика:\n\n"
    msg += f"Пройдено тестов: {stats['total_tests']}\n"
    msg += f"Всего ответов: {stats['total_answers']}\n"
    msg += f"Правильных ответов: {stats['correct_answers']}\n"
    msg += f"Точность: {stats['accuracy']}%\n\n"
    
    if stats["skills"]:
        msg += "По навыкам:\n"
        for skill, data in stats["skills"].items():
            msg += f"  {skill}: {data['correct']}/{data['total']} ({data['percent']}%)\n"
    
    return msg


def get_test_history_command(user_id: int) -> str:
    """Команда для просмотра истории тестов."""
    history = get_test_history(user_id)
    
    if not history:
        return "У вас нет истории тестов."
    
    msg = "📚 История тестов:\n\n"
    
    for i, test in enumerate(history[:10], 1):  # Последние 10 тестов
        status = "✅" if test["is_ready"] else "❌"
        msg += f"{i}. {status} {test['test_name']}\n"
        msg += f"   Результат: {test['total_score']} ({test['overall_percent']}%)\n"
        msg += f"   Дата: {test['timestamp'][:10] if test['timestamp'] else 'N/A'}\n\n"
    
    return msg


def restart_command(user_id: int) -> str:
    """Команда для перезапуска (очистка истории)."""
    # Удаляем активную сессию
    clear_test_session(user_id)
    
    return (
        "Перезапуск completed. 🔄\n\n"
        "Чтобы начать заново, пришли новое описание стажировки."
    )


def main():
    print("MAX-бот для проверки стажировок запущен!")

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
                text = message.get("body", {}).get("text", "")

                if user_id is None:
                    continue

                print(f"Получено сообщение от {user_id}: {text[:50]}...")

                # Обрабатываем сообщение
                response_text = process_user_message(user_id, text)
                
                # Отправляем ответ
                send_message(user_id, response_text)
                print(f"Ответ отправлен пользователю {user_id}")

        except Exception as error:
            print(f"Ошибка: {error}")
            time.sleep(5)


if __name__ == "__main__":
    main()